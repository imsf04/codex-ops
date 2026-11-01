"""Read explicitly selected local rollouts without exposing their message bodies."""
import json
from pathlib import Path


def _session(record, current):
    if record.get('type') == 'session_meta':
        value = record.get('payload', {})
        return value.get('id') or value.get('session_id') or current
    return current


def read(paths, max_records=100000):
    """Keep source session identity for inherited records; never change originals."""
    if not 1 <= len(paths) <= 32:
        raise ValueError('Select 1..32 rollout files')
    result = []
    for path in paths:
        result.extend(_read_file(Path(path), max_records - len(result)))
    return result


def _read_file(path, remaining):
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Rollout exceeds 64 MiB; select a bounded export')
    result, session = [], None
    with path.open(encoding='utf-8') as source:
        for line in source:
            record = _decode_line(line)
            if record is None:
                continue
            session = _session(record, session)
            result.append(dict(record, _sessionId=session))
            if len(result) > remaining:
                raise ValueError('Rollout record budget exceeded')
    return result


def _decode_line(line):
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        if line.endswith('\n'):
            raise
        return None  # An active rollout can have an unfinished final append.


def identity(record):
    payload = record.get('payload', {})
    return payload.get('session_id') or payload.get('thread_id') or record.get('_sessionId')


def parents(records):
    result = {}
    for record in records:
        if record.get('type') == 'session_meta':
            meta = record['payload']
            key = meta.get('id') or meta.get('session_id')
            result[key] = meta.get('parent_thread_id') or meta.get('forked_from_id')
    return result


def root(session, ancestry):
    seen = set()
    while ancestry.get(session):
        if session in seen:
            return None
        seen.add(session)
        session = ancestry[session]
    return session
