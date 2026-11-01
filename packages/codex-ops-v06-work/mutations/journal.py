"""Durable write-ahead records and OS-released locks; no automatic recovery."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import uuid
from .paths import MAX_BYTES, RESERVED, digest, read, require, target
from .planning import encoded, validate


def write_json(path, value):
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    with temporary.open('xb') as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _directory(root, create):
    path = target(root, RESERVED, internal=True)
    if not path.exists() and create:
        path.mkdir()
        write_json(path / 'owner.json', {'format': 'codex-ops-mutations', 'version': 1})
    require(path.is_dir(), 'Mutation journal directory does not exist')
    marker = target(root, f'{RESERVED}/owner.json', internal=True)
    require(read(marker) == encoded({'format': 'codex-ops-mutations', 'version': 1}), 'Existing journal directory is not owned by Codex Ops')
    return path


def _backup(root, directory, name, expected, index):
    data = read(target(root, name))
    require(digest(data) == expected, 'Source changed while preparing recovery snapshot')
    if data is None:
        return None
    backup = f'{index}.bin'
    with (directory / backup).open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return backup


def create(plan):
    root = validate(plan)
    job_id = uuid.uuid4().hex
    directory = _directory(root, True) / job_id
    directory.mkdir()
    snapshots = {}
    for item in plan['items']:
        for name, revision in item['before'].items():
            snapshots[name] = _backup(root, directory, name, revision, len(snapshots))
    record = {'version': 1, 'id': job_id, 'plan': plan, 'backups': snapshots, 'phase': 'ready', 'error': None}
    write_json(directory / 'journal.json', record)
    return directory, record


def load(root, job_id):
    require(isinstance(job_id, str) and re.fullmatch('[0-9a-f]{32}', job_id), 'Invalid journal ID')
    directory = _directory(root, False) / job_id
    path = target(root, str(directory / 'journal.json'), internal=True)
    require(path.stat().st_size <= 10 * MAX_BYTES, 'Journal exceeds its size limit')
    value = json.loads(path.read_text(encoding='utf-8'))
    require(value['id'] == job_id and validate(value['plan']) == root, 'Journal identity does not match root')
    return directory, value


def save(directory, record, phase, error=None):
    record.update(phase=phase, error=error)
    write_json(directory / 'journal.json', record)


def _acquire(stream):
    if os.name == 'nt':
        import msvcrt
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


@contextmanager
def locked(root, directory):
    path = target(root, str(directory / 'lock'), internal=True)
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        _acquire(stream)
        yield
