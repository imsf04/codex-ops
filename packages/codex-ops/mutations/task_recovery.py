"""Explicit recovery of a tracked child whose native effect stopped mid-step."""
from . import engine, journal, task_journal
from .paths import require
from .task_execution import expected, file_plan, observation


def _index(record):
    pending = record.get('recovery')
    if pending is not None:
        return pending['index']
    return record['cursor'] - 1 if record['direction'] == 'rollback' else record['cursor']


def _child(root, record):
    index = _index(record)
    require(type(index) is int and 0 <= index < len(record['plan']['steps']), 'No interrupted child step to recover')
    step = record['plan']['steps'][index]
    require(step['operation'] not in ('mkdir', 'rmdir'), 'Uncertain directory effect requires inspection')
    identity = record['children'].get(str(index))
    require(identity is not None, 'Missing child journal; inspect before recovery')
    _, child = journal.load(root, identity)
    require(child['plan'] == file_plan(root, step), 'Child journal differs from its parent step')
    return index, identity, step


def _without(values, names):
    return {name: value for name, value in values.items() if name not in names}


def _validate_other_paths(root, record, step):
    changed = set(step['before']) | set(step['after'])
    require(_without(observation(root, record), changed) == _without(expected(record), changed),
            'Task paths outside the interrupted child changed; inspect before recovery')


def _validate_child(root, identity):
    state = engine.inspect(root, identity)
    require(state['conflicts'] == 0, 'Interrupted child has conflicting file content; inspect before recovery')


def _start(folder, record, index, action):
    record['recovery'] = {'index': index, 'action': action}
    if action == 'rollback':
        record['direction'] = 'rollback'
    task_journal.save(folder, record, 'recovering')


def _finish(root, folder, record, index, action):
    record['cursor'] = index if action == 'rollback' else index + 1
    record.pop('recovery', None)
    require(observation(root, record) == expected(record), 'Recovered child does not match its parent frontier')
    task_journal.save(folder, record, 'ready')


def recover(root, folder, record, action):
    index, identity, step = _child(root, record)
    _validate_other_paths(root, record, step)
    _validate_child(root, identity)
    _start(folder, record, index, action)
    operation = engine.rollback if action == 'rollback' else engine.resume
    result = operation(root, identity)
    terminal = 'rolled-back' if action == 'rollback' else 'completed'
    require(result['status'] == terminal, 'Child recovery needs inspection: ' + identity)
    _finish(root, folder, record, index, action)
