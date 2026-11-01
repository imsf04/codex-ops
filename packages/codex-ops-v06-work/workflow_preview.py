"""Preserve actionable workflow evidence inside bounded observation receipts."""
from reducers import encode
import query_preview
from record_preview import preview as records


def _row(label, value, pointer):
    return {'label': label, 'value': value, 'pointer': pointer}


def _diagnostics(value):
    return [_row('diagnostic', item, f'/diagnostics/{index}')
            for index, item in enumerate(value.get('diagnostics', []))]


def _documents(value):
    rows = []
    for index, item in enumerate(value.get('items', [])):
        for entry in item.get('evidence', {}).get('items', []):
            rows.append(_row('document', {'resultRef': item['resultRef'], **entry}, f'/items/{index}/evidence'))
    return rows


def _incremental(value):
    rows = []
    for index, item in enumerate(value.get('items', [])):
        summary = {key: item.get(key) for key in ('path', 'mode', 'revision', 'sameFileRevision', 'omittedUnchangedLines')}
        rows.append(_row('file', summary, f'/items/{index}'))
        rows.extend(_row('change', change, f'/items/{index}/changes/{number}')
                    for number, change in enumerate(item.get('changes', [])))
    return rows


def _candidates(value, operation):
    functions = {'diagnose': _diagnostics, 'documents': _documents, 'incremental': _incremental}
    return functions.get(operation, lambda _: [])(value)


def _context(result, value, budget):
    context = records(value.get('context', {}), 1200)
    candidate = {**result, 'context': context}
    return candidate if context is not None and len(encode(candidate).encode()) <= budget else result


def preview(value, operation, budget=3500):
    result = {'kind': 'workflow-evidence', 'operation': operation, 'status': value.get('status'),
              'snapshotRef': value.get('snapshotRef'), 'evidence': [], 'contextPath': '/context',
              'nextAction': value.get('nextAction', 'Read selected fields from the saved workflow result'),
              'previewOnly': True}
    candidates = _candidates(value, operation)
    for row in candidates:
        if len(encode({**result, 'evidence': [*result['evidence'], row]}).encode()) > budget - 1400:
            break
        result['evidence'].append(row)
    result['omittedPreviewRows'] = len(candidates) - len(result['evidence'])
    return _context(result, value, budget)


def capture(store, value, operation):
    if operation == 'locate':
        return query_preview.capture(store, value, 'search')
    receipt = store.capture(value)
    if receipt.get('kind') == 'reference':
        receipt['preview'] = preview(value, operation)
    return receipt
