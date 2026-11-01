"""Native-shell task steps and reverse recovery, with explicit frontier checks."""
from . import engine, journal, task_journal, task_tree as tree, task_directories
from .paths import digest, require, target
from .planning import encoded


def file_plan(root, step):
    operation = step['operation']
    args = step['args']
    name = args['path']
    if operation in ('write', 'edit', 'replace'):
        native = {'path': name, 'content': step['content'], 'expectedRevision': step['before'][name]}
        tool = 'write_file'
    else:
        native = {**args, 'expectedRevision': step['before'][name]}
        tool = operation
    after = {key: value or 'absent' for key, value in step['after'].items()}
    item = {'operation': operation, 'tool': tool, 'args': native, 'before': step['before'], 'after': after}
    body = {'version': 1, 'root': str(root), 'items': [item]}
    return {**body, 'planDigest': digest(encoded(body))}


def ensure_child(root, folder, record, step):
    key = str(record['cursor'])
    if key not in record['children']:
        _, child = journal.create(file_plan(root, step))
        record['children'][key] = child['id']
        task_journal.save(folder, record, 'applying')
    return record['children'][key]


def execute(root, folder, record, step):
    operation = step['operation']
    if operation in ('mkdir', 'rmdir'):
        task_directories.execute(root, step['args']['path'], operation == 'mkdir')
        return
    result = engine.resume(root, ensure_child(root, folder, record, step))
    require(result['status'] == 'completed', 'Child mutation needs inspection: ' + result['journalId'])


def reverse(root, folder, record, step, index):
    operation = step['operation']
    if operation in ('mkdir', 'rmdir'):
        task_directories.execute(root, step['args']['path'], operation != 'mkdir')
        return
    identity = record['children'].get(str(index))
    require(identity is not None, 'Missing child journal; inspect before recovery')
    result = engine.rollback(root, identity)
    require(result['status'] == 'rolled-back', 'Child rollback needs inspection: ' + identity)


def observation(root, record):
    return tree.observe(root, record['plan']['roots'])


def expected(record, index=None):
    return tree.frontier(record['plan'], record['cursor'] if index is None else index)


def check(root, record):
    require(observation(root, record) == expected(record), 'Task frontier changed; inspect the explicit paths before recovery')


def active_child(record):
    recovery = record.get('recovery')
    if recovery is not None:
        return record['children'].get(str(recovery['index']))
    index = record['cursor'] - 1 if record['direction'] == 'rollback' else record['cursor']
    return record['children'].get(str(index))


def _next_frontier(root, folder, record, current):
    index = record['cursor'] - 1 if record['direction'] == 'rollback' else record['cursor'] + 1
    if not 0 <= index <= len(record['plan']['steps']):
        return False
    if current != expected(record, index):
        return False
    record['cursor'] = index
    task_journal.save(folder, record, 'ready')
    return True


def reconcile(root, folder, record, action='forward'):
    from .task_recovery import recover
    if record.get('recovery') is not None:
        recover(root, folder, record, action)
        return
    current = observation(root, record)
    if current == expected(record):
        return
    if not _next_frontier(root, folder, record, current):
        recover(root, folder, record, action)
