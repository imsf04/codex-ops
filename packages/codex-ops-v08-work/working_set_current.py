"""Bounded fresh file windows acquired during the existing revision check."""
import json
import os

WINDOW_LINES = 64


def _line(item, path):
    if not isinstance(item, dict):
        return None
    source = item.get('source', {})
    if not isinstance(source, dict) or not isinstance(source.get('path'), str):
        return None
    if os.path.normcase(os.path.normpath(source['path'])) != path:
        return None
    location = item.get('location', {})
    return location.get('line') if isinstance(location, dict) else None


def _items(value):
    items = value.get('items') if isinstance(value, dict) else None
    return items[:4000] if isinstance(items, list) else []


def request(source, value):
    path = os.path.normcase(os.path.normpath(source['path']))
    lines = [_line(item, path) for item in _items(value)]
    known = [line for line in lines if type(line) is int and line > 0]
    return {'path': source['path'], **_window(known)}


def _window(lines):
    if not lines:
        return {'offset': 1, 'limit': WINDOW_LINES}
    offset = max(1, min(lines) - 2)
    return {'offset': offset, 'limit': min(WINDOW_LINES, max(lines) - offset + 3)}


def observed(row, query):
    return {**row, 'requestedWindow': {'offset': query['offset'], 'limit': query['limit']},
            'coverageMeaning': 'Fresh native read window; saved lines outside this window are not refreshed.'}


def bounded(item, remaining, save):
    result = dict(item)
    current = result.pop('currentEvidence')
    size = len(json.dumps(current, ensure_ascii=False).encode('utf-8'))
    if size <= remaining:
        return {**result, 'currentEvidence': current, 'currentEvidenceOmitted': False}, remaining - size
    result['currentEvidenceOmitted'] = True
    result['currentRead'] = {key: current[key] for key in ('path', 'revision', 'requestedWindow') if key in current}
    if callable(save):
        result['currentEvidenceRef'] = save(current)
    return result, remaining
