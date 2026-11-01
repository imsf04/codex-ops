"""Durable parent journals; file effects retain the established child journals."""
import json
from pathlib import Path
import re
import uuid
from . import journal
from .paths import MAX_BYTES, require, target
from .task_planning import validate
from .task_tree import RESERVED

MARKER = {'format': 'codex-ops-tasks', 'version': 1}


def directory(root, create=False):
    result = target(root, RESERVED, internal=True)
    if not result.exists() and create:
        result.mkdir()
        journal.write_json(result / 'owner.json', MARKER)
    require(result.is_dir(), 'Task journal directory does not exist')
    marker = target(root, str(result / 'owner.json'), internal=True)
    require(json.loads(marker.read_text(encoding='utf-8')) == MARKER, 'Task journal directory is not owned')
    return result


def create(plan):
    root = validate(plan)
    identity = uuid.uuid4().hex
    folder = directory(root, True) / identity
    folder.mkdir()
    record = {'id': identity, 'version': 1, 'plan': plan, 'cursor': 0, 'phase': 'ready',
              'children': {}, 'direction': 'forward', 'error': None}
    journal.write_json(folder / 'journal.json', record)
    return folder, record


def load(root, identity):
    require(isinstance(identity, str) and re.fullmatch('[a-f0-9]{32}', identity), 'Invalid task ID')
    folder = directory(root) / identity
    path = target(root, str(folder / 'journal.json'), internal=True)
    require(path.stat().st_size <= 10 * MAX_BYTES, 'Task journal exceeds 10 MiB')
    record = json.loads(path.read_text(encoding='utf-8'))
    require(record['id'] == identity and validate(record['plan']) == root, 'Task identity mismatch')
    require(type(record['cursor']) is int and 0 <= record['cursor'] <= len(record['plan']['steps']), 'Invalid task cursor')
    return folder, record


def save(folder, record, phase, error=None):
    record.update(phase=phase, error=error)
    journal.write_json(folder / 'journal.json', record)


def cancelled(root, folder):
    flag = target(root, str(folder / 'cancel.json'), internal=True)
    return flag.exists()


def cancel(root, identity):
    folder, record = load(root, identity)
    journal.write_json(folder / 'cancel.json', {'requested': True})
    return {'status': 'cancel-requested', 'taskId': identity, 'effectState': 'unknown',
            'completedSteps': record['cursor'], 'cancellation': 'cooperative-before-next-step',
            'nextAction': 'Inspect status after the active primitive returns; this does not kill a native process.'}


def clear_cancel(root, folder):
    flag = target(root, str(folder / 'cancel.json'), internal=True)
    flag.unlink(missing_ok=True)
