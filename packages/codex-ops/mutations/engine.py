"""Native-shell-only mutation execution and explicit postcondition-based recovery."""
from pathlib import Path
import subprocess
from . import journal, worker
from .paths import Conflict, digest, read, require, root_path, states, target
from .planning import validate


def _item_state(root, item):
    current = states(root, item['before'])
    if current == item['before']:
        return 'before'
    if current == item['after']:
        return 'after'
    if all(current[name] in (before, item['after'][name]) for name, before in item['before'].items()):
        return 'partial'
    return 'conflict'


def _preflight(root, items, allowed):
    observed = [_item_state(root, item) for item in items]
    require(all(value in allowed for value in observed), 'File state changed; inspect before applying or recovering')
    return observed


def receipt(root, record):
    observed = [_item_state(root, item) for item in record['plan']['items']]
    return {'status': record['phase'], 'journalId': record['id'], 'root': str(root),
            'operationCount': len(observed), 'before': observed.count('before'), 'after': observed.count('after'),
            'partial': observed.count('partial'), 'conflicts': observed.count('conflict'), 'error': record['error'],
            'effectState': _effect(record, observed), 'rollbackComplete': record['phase'] == 'rolled-back',
            'nextAction': 'Inspect status; resume or rollback explicitly. Never repeat apply after an uncertain result.'}


def _effect(record, observed):
    if record['phase'] == 'needs-inspection' or any(value in ('conflict', 'partial') for value in observed):
        return 'unknown'
    return 'applied' if 'after' in observed else 'none'


def _execute(root, item):
    if _item_state(root, item) == 'partial':
        result = _finish_move(root, item)
    else:
        result = worker.invoke(root, item['tool'], item['args'])
    require(states(root, item['after']) == item['after'], 'Worker postconditions differ; inspect journal')
    return result


def _finish_move(root, item):
    require(item['tool'] == 'move', 'Partial operation requires explicit rollback')
    args = item['args']
    expected = {args['path']: args['expectedRevision'], args['to']: args['expectedRevision']}
    require(states(root, expected) == expected, 'Partial move cannot resume; inspect or roll back')
    return worker.invoke(root, 'remove', {'path': args['path'], 'expectedRevision': args['expectedRevision']})


def _apply_remaining(root, directory, record):
    require(record['phase'] != 'rolled-back' and record.get('direction') != 'rollback', 'Rollback started; continue rollback or prepare a new plan')
    if record['phase'] == 'completed':
        return
    _preflight(root, record['plan']['items'], {'before', 'after', 'partial'})
    for item in record['plan']['items']:
        if _item_state(root, item) == 'after':
            continue
        journal.save(directory, record, 'applying')
        _execute(root, item)
    journal.save(directory, record, 'completed')


def _run(root, directory, record, action):
    with journal.locked(root, directory):
        _, record = journal.load(root, record['id'])
        try:
            action(root, directory, record)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            journal.save(directory, record, 'needs-inspection', str(exc))
        return receipt(root, record)


def apply(plan):
    root = validate(plan)
    _preflight(root, plan['items'], {'before'})
    directory, record = journal.create(plan)
    return _run(root, directory, record, _apply_remaining)


def inspect(root, job_id):
    root = root_path(root)
    _, record = journal.load(root, job_id)
    return receipt(root, record)


def resume(root, job_id):
    root = root_path(root)
    directory, record = journal.load(root, job_id)
    require(record['phase'] != 'rolled-back' and record.get('direction') != 'rollback', 'Rollback started; continue rollback or prepare a new plan')
    return _run(root, directory, record, _apply_remaining)


def _backup_path(root, directory, record, name):
    backup = record['backups'][name]
    require(isinstance(backup, str) and backup == Path(backup).name, 'Invalid snapshot filename')
    path = target(root, str(directory / backup), internal=True)
    expected = next(item['before'][name] for item in record['plan']['items'] if name in item['before'])
    require(digest(read(path)) == expected, 'Recovery snapshot is missing or modified')
    return path


def _restore_file(root, directory, record, name, before, after):
    if before == 'absent':
        worker.invoke(root, 'remove', {'path': name, 'expectedRevision': after})
        return
    backup = _backup_path(root, directory, record, name)
    _restore_present(root, backup, name, before, after)


def _restore_present(root, backup, name, before, after):
    if after == 'absent':
        worker.invoke(root, 'copy', {'path': str(backup), 'to': name, 'expectedRevision': before}, internal=True)
    else:
        data = read(backup)
        require(digest(data) == before, 'Recovery snapshot changed while reading')
        content = data.decode('utf-8')
        worker.invoke(root, 'write_file', {'path': name, 'content': content, 'expectedRevision': after})


def _rollback(root, directory, record):
    _preflight(root, record['plan']['items'], {'before', 'after', 'partial'})
    record['direction'] = 'rollback'
    for item in reversed(record['plan']['items']):
        if _item_state(root, item) == 'before':
            continue
        journal.save(directory, record, 'rolling-back')
        for name, before in item['before'].items():
            current = states(root, [name])[name]
            if current != before:
                _restore_file(root, directory, record, name, before, item['after'][name])
    journal.save(directory, record, 'rolled-back')


def rollback(root, job_id):
    root = root_path(root)
    directory, record = journal.load(root, job_id)
    return _run(root, directory, record, _rollback)
