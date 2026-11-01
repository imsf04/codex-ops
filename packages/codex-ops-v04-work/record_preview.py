"""Useful bounded previews for native file/search/document records."""
import json

FACTS = ('status', 'complete', 'truncated', 'scanComplete', 'pageComplete', 'nextOffset',
         'nextIndex', 'pending', 'matchedTotal', 'matchedObserved', 'skippedFiles',
         'scope', 'excludedContent', 'columns', 'error')
ROW_KEYS = ('path', 'line', 'row', 'page', 'text', 'cells', 'view', 'offset', 'error')


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())


def _facts(value):
    return {key: value[key] for key in FACTS if key in value}


def _row(value):
    if isinstance(value, str):
        return {'path': value[:300]}
    if not isinstance(value, dict):
        return None
    return {key: _short(value[key]) for key in ROW_KEYS if key in value}


def _short(value):
    if isinstance(value, str):
        return value if len(value) <= 240 else value[:240] + ' …'
    if isinstance(value, list):
        return [_short(item) for item in value[:8]]
    return value


def _rows(items):
    indices = list(range(min(len(items), 10)))
    if len(items) > 10:
        indices.append(len(items) - 1)
    return [{'index': index, **row} for index in indices if (row := _row(items[index]))]


def _file(value, index):
    return {'path': value['path'], 'revision': value.get('revision'),
            'recordsPath': f'/items/{index}/items', **_facts(value),
            'returnedLines': len(value['items']), 'sample': _rows(value['items'])}


def _file_batch(items):
    return bool(items) and all(isinstance(row, dict) and 'path' in row and
                               isinstance(row.get('items'), list) for row in items)


def _native(value):
    return isinstance(value, dict) and isinstance(value.get('items'), list) and 'phase' in value


def preview(value, budget):
    if not _native(value):
        return None
    items = value['items']
    if _file_batch(items):
        samples = [_file(row, index) for index, row in enumerate(items[:4])]
        result = {'kind': 'file-ranges', 'files': samples}
    else:
        result = {'kind': 'records', 'recordsPath': '/items', 'sample': _rows(items)}
    result.update({**_facts(value), 'returnedItems': len(items), 'previewOnly': True})
    return _fit(result, budget)


def _shrink(result):
    rows = result.get('sample', result.get('files', []))
    if rows and result.get('files'):
        if rows[-1]['sample']:
            rows[-1]['sample'].pop()
            return True
    if rows:
        rows.pop()
        return True
    return False


def _fit(result, budget):
    while _size(result) > budget:
        result['clipped'] = True
        if not _shrink(result):
            return None  # Generic preview preserves oversized metadata using its own bounded policy.
    return result
