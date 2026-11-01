"""Keep each document's outcome visible before optional source excerpts."""
from reducers import encode
import evidence_selection


def outcome(item):
    result = item.get('result') or {}
    row = {key: item[key] for key in ('index', 'operation', 'status', 'sourceComplete', 'routing', 'resultRef') if key in item}
    failure = item.get('error') or result.get('error')
    if failure:
        row['error'] = failure_view(failure)
    _details(row, item, result)
    return row


def _details(row, item, result):
    found = item.get('evidence', {})
    columns = found.get('columns', result.get('columns'))
    if columns is not None:
        row['columns'] = columns
    if not item.get('sourceComplete'):
        row['sourceCoverage'] = evidence_selection.context(item.get('sourceCoverage', result))
    if found:
        row['evidenceCoverage'] = {key: found[key] for key in ('omittedMatches', 'scanComplete') if key in found}
    _failure_details(row, result)


def _failure_details(row, result):
    failures = native_failures(result)
    if failures:
        row.update(failures=failures[:8], omittedFailures=max(0, len(failures) - 8))


def native_failures(value):
    pending, failures = [value], []
    while pending:
        current = pending.pop()
        if not isinstance(current, dict):
            continue
        failure = _native_failure(current)
        if failure:
            failures.append(failure)
        pending.extend(_native_children(current))
    return failures


def _native_failure(value):
    if value.get('status') not in ('error', 'failed', 'rejected'):
        return None
    failure = value.get('error')
    if not isinstance(failure, dict):
        return None
    return {'path': value.get('path'), 'error': failure_view(failure)}


def _native_children(value):
    items = value.get('items', [])
    if not isinstance(items, list):
        return []
    return [child for child in items if isinstance(child, dict) and 'status' in child]


def failure_view(value):
    result = dict(value)
    message = result.get('message')
    if isinstance(message, str) and len(message) > 400:
        result.update(message=message[:400], clipped=True)
    return result


def _children(value, pointer):
    if isinstance(value, dict):
        return [(pointer + '/' + _pointer(key), child) for key, child in value.items()]
    if isinstance(value, list):
        return [(pointer + '/' + str(index), child) for index, child in enumerate(value)]
    return []


def _pointer(key):
    return str(key).replace('~', '~0').replace('/', '~1')


def excerpts(value, maximum=8, text_limit=800):
    pending, rows, scanned = [('', value)], [], 0
    while pending and scanned < 4000:
        pointer, current = pending.pop()
        scanned += 1
        row = _excerpt(pointer, current, text_limit)
        if row is not None:
            rows.append(row)
        pending.extend(reversed(_children(current, pointer)))
    selected = rows[:maximum]
    result = {'items': selected, 'omittedMatches': len(rows) - len(selected), 'scanComplete': not pending}
    if isinstance(value, dict) and 'columns' in value:
        result['columns'] = value['columns']
    return result


def _excerpt(pointer, value, text_limit=800):
    if pointer.endswith('/text') and isinstance(value, str):
        return {'pointer': pointer, 'text': value[:text_limit],
                'clipped': text_limit is not None and len(value) > text_limit}
    if isinstance(value, dict) and isinstance(value.get('cells'), list):
        return _table(pointer, value, text_limit)
    return None


def _table(pointer, value, text_limit):
    if text_limit is None or len(encode(value).encode()) <= 1200:
        return {'pointer': pointer, 'row': value}
    return {'pointer': pointer, 'text': encode(value)[:800], 'clipped': True}


def evidence(item):
    found = item.get('evidence', {}).get('items', [])
    rows = [row for row in found if 'text' in row or 'row' in row]
    if rows:
        return rows
    return excerpts(item.get('result', {}), maximum=4000, text_limit=None)['items']


def summary(value):
    return [outcome(item) for item in value.get('items', [])]
