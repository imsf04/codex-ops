"""Authorize source references again and optionally check current file revisions."""
import evidence_index_rows
from pathlib import Path
from store import ReferenceUnavailable
from workflow_validation import callback, options, require, text


def request(item):
    options(item, ('ref', 'label', 'path', 'revision'))
    result = {'ref': text(item.get('ref'), 'source ref', 256),
              'label': text(item.get('label', ''), 'source label', 500, empty=True)}
    if 'path' in item:
        result['path'] = text(item['path'], 'path', 4096)
        result['revision'] = text(item.get('revision'), 'revision', 128)
    else:
        require('revision' not in item, 'revision requires path')
    return result


def _current(root, source, invoke):
    result = callback(invoke, 'invoke')(root, 'read', {'files': [
        {'path': source['path'], 'offset': 1, 'limit': 1}]})
    rows = result.get('items', [])
    require(bool(rows), 'Current source revision unavailable')
    first = rows[0]
    require(first.get('status') == 'completed', 'Current source read failed')
    require(bool(first.get('revision')), 'Current source revision unavailable')
    require(bool(first.get('path')), 'Current source path unavailable')
    return first


def _children(value):
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return value
    return []


def _matches(value, path, revision):
    if not isinstance(value, dict):
        return False
    return value.get('path') == path and value.get('revision') == revision


def _origin(value, path, revision):
    pending, visited = [value], 0
    while pending and visited < 4000:
        item = pending.pop()
        visited += 1
        if _matches(item, path, revision):
            return True
        pending.extend(_children(item))
    return False


def _fresh(root, source, invoke, value):
    if 'path' not in source:
        return 'saved-observation', None
    current = _current(root, source, invoke)
    path = current['path']
    expected = (Path(root) / source['path']).resolve()
    require(Path(path).resolve() == expected, 'Current source path differs from requested source')
    require(_origin(value, path, source['revision']), 'Observation does not attest the requested file and revision')
    revision = current['revision']
    if revision != source['revision']:
        return 'stale', revision
    return 'current', revision


def resolve(root, source, invoke, load):
    try:
        value = load(source['ref'])
        state, revision = _fresh(root, source, invoke, value)
        if state == 'stale':
            return {**source, 'state': state, 'currentRevision': revision}
        return _available(source, value, state, revision)
    except (ValueError, OSError, KeyError, ReferenceUnavailable) as exc:
        return {**source, 'state': 'unavailable', 'reason': str(exc)}


def _available(source, value, state, revision):
    digest = evidence_index_rows.fingerprint(value)
    expected = source.get('observationDigest', digest)
    require(digest == expected, 'Saved observation changed; start a new working set')
    return {**source, 'state': state, 'currentRevision': revision,
            'observationDigest': digest, 'value': value}


def manifest(value):
    return {key: item for key, item in value.items()
            if key in ('ref', 'label', 'path', 'revision', 'observationDigest')}
