"""Cooperative staged tasks; native permissions remain the execution boundary."""
import subprocess
from . import journal, task_execution as execution, task_journal as tasks
from .paths import require, root_path
from .task_planning import plan as prepare, validate


def receipt(root, record):
    current = execution.observation(root, record)
    unchanged = current == record['plan']['initial']
    return {'status': record['phase'], 'taskId': record['id'], 'root': str(root),
            'completedSteps': record['cursor'], 'totalSteps': len(record['plan']['steps']),
            'frontierMatches': current == execution.expected(record),
            'effectState': 'none' if unchanged else 'applied' if record['phase'] == 'completed' else 'unknown',
            'rollbackComplete': record['phase'] == 'rolled-back' and unchanged,
            'error': record['error'], 'direction': record['direction'],
            'activeChildJournal': execution.active_child(record),
            'nextAction': 'Use explicit status/resume/rollback; cancellation stops before the next primitive, never kills a process.'}


def _forward(root, folder, record):
    require(record['direction'] == 'forward' and record['phase'] != 'rolled-back', 'Rollback already started')
    execution.reconcile(root, folder, record)
    while record['cursor'] < len(record['plan']['steps']):
        if tasks.cancelled(root, folder):
            tasks.save(folder, record, 'cancelled')
            return
        execution.check(root, record)
        tasks.save(folder, record, 'applying')
        execution.execute(root, folder, record, record['plan']['steps'][record['cursor']])
        record['cursor'] += 1
        tasks.save(folder, record, 'ready')
    execution.check(root, record)
    tasks.save(folder, record, 'completed')


def _backward(root, folder, record):
    execution.reconcile(root, folder, record, 'rollback')
    record['direction'] = 'rollback'
    while record['cursor']:
        execution.check(root, record)
        tasks.save(folder, record, 'rolling-back')
        index = record['cursor'] - 1
        execution.reverse(root, folder, record, record['plan']['steps'][index], index)
        record['cursor'] = index
        tasks.save(folder, record, 'ready')
    execution.check(root, record)
    tasks.save(folder, record, 'rolled-back')


def _run(root, folder, identity, action, clear=False):
    with journal.locked(root, folder):
        _, record = tasks.load(root, identity)
        if clear:
            tasks.clear_cancel(root, folder)
        try:
            action(root, folder, record)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            tasks.save(folder, record, 'needs-inspection', str(exc))
        return receipt(root, record)


def apply(value, started=None):
    root = validate(value)
    require(prepare(root, value['stages'], value['owner']) == value, 'Task source or plan changed before execution')
    folder, record = tasks.create(value)
    if started:
        started({'status': 'started', 'taskId': record['id'], 'root': str(root), 'effectState': 'none'})
    return _run(root, folder, record['id'], _forward)


def inspect(root, identity):
    root = root_path(root)
    _, record = tasks.load(root, identity)
    return receipt(root, record)


def resume(root, identity):
    root = root_path(root)
    folder, record = tasks.load(root, identity)
    return _run(root, folder, record['id'], _forward, clear=True)


def rollback(root, identity):
    root = root_path(root)
    folder, record = tasks.load(root, identity)
    return _run(root, folder, record['id'], _backward)


def cancel(root, identity):
    return tasks.cancel(root_path(root), identity)
