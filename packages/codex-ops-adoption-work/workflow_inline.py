"""Recognize bounded, self-contained workflow displays without changing any value."""
import json

MAX_BYTES = 8192
STATUSES = ('completed', 'partial')
DOCUMENT_OPERATIONS = ('read', 'read_table', 'read_docx', 'read_pdf', 'inspect')


def _failed(value):
    return bool(value.get('isError') or value.get('error') or
                value.get('status') in ('error', 'failed', 'failure'))


def _safe(value):
    if isinstance(value, dict):
        return _safe_mapping(value)
    if isinstance(value, list):
        return all(_safe(child) for child in value)
    return True


def _safe_mapping(value):
    return not _failed(value) and all(_safe(child) for child in value.values())


def _text_block(value):
    return isinstance(value, dict) and value.get('type') == 'text'


def _transport(value):
    if not isinstance(value, dict):
        return False
    blocks = value.get('content')
    if blocks is None:
        return True
    if not isinstance(blocks, list) or len(blocks) != 1:
        return False
    return _text_block(blocks[0])


def _native_result(value):
    return (isinstance(value, dict) and value.get('status') in STATUSES
            and isinstance(value.get('items'), list))


def _evidence_row(value):
    if not isinstance(value, dict):
        return False
    if isinstance(value.get('text'), str) and value['text']:
        return True
    row = value.get('row')
    return isinstance(row, dict) and isinstance(row.get('cells'), list)


def _document_content(value):
    if _native_result(value.get('result')):
        return True
    evidence = value.get('evidence')
    if not isinstance(evidence, dict) or not isinstance(evidence.get('items'), list):
        return False
    return any(_evidence_row(row) for row in evidence['items'])


def _document_shape(value, index):
    return (isinstance(value, dict) and value.get('index') == index
            and value.get('operation') in DOCUMENT_OPERATIONS
            and value.get('status') in STATUSES
            and type(value.get('sourceComplete')) is bool)


def _document_items(value):
    items = value.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 4:
        return None
    if value.get('requestCount') != len(items):
        return None
    return items


def _documents(value):
    items = _document_items(value)
    return (items is not None and all(_document_shape(row, i) for i, row in enumerate(items))
            and any(_document_content(row) for row in items))


def _diagnostic(value):
    if not isinstance(value, dict):
        return False
    return (type(value.get('line')) is int and value['line'] > 0
            and isinstance(value.get('text'), str) and bool(value['text']))


def _diagnose(value):
    rows = value.get('diagnostics')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 40:
        return False
    return _diagnostic_context(value) and all(_diagnostic(row) for row in rows)


def _diagnostic_context(value):
    return isinstance(value.get('context'), dict) and isinstance(value.get('sourceRequests'), list)


def _workflow(value):
    if not isinstance(value, dict):
        return False
    if value.get('effectState') != 'none' or value.get('status') not in STATUSES:
        return False
    validate = {'documents': _documents, 'diagnose': _diagnose}.get(value.get('operation'))
    return validate(value) if validate else False


def _valid_payload(analysis):
    return (_workflow(analysis['value']) and _safe(analysis['metadata'])
            and _safe(analysis['value']))


def eligible(text, analysis):
    if len(text.encode('utf-8')) > MAX_BYTES:
        return False
    if not _valid_payload(analysis):
        return False
    try:
        original = json.loads(text)
    except (ValueError, RecursionError):
        return False
    return _transport(original) and _safe(original)
