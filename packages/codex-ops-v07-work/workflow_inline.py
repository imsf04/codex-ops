"""Recognize bounded, self-contained workflow displays without changing any value."""
import json
import re

MAX_BYTES = 8192
PACKET_MAX_BYTES = 24576
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
    validate = {'documents': _documents, 'diagnose': _diagnose, 'investigate': _packet,
                'evidence': _packet, 'working_set': _packet, 'verify': _verify}.get(value.get('operation'))
    return validate(value) if validate else False


def _packet(value):
    return (_packet_contract(value)
            and value.get('evidenceState') in ('collected', 'needs_anchor', 'no_match', 'partial', 'unavailable')
            and _packet_items(value.get('items')))


def _packet_items(items):
    return isinstance(items, list) and all(_packet_item(item) for item in items)


def _packet_item(item):
    if not isinstance(item, dict):
        return False
    if item.get('kind') == 'reference-excerpt':
        return _reference_excerpt(item)
    if item.get('kind') == 'working-source':
        return _working_source(item)
    return isinstance(item.get('text'), str) and _packet_location(item)


def _reference_excerpt(item):
    source, location = item.get('source'), item.get('location')
    if not isinstance(source, dict) or not isinstance(location, dict):
        return False
    return isinstance(item.get('text'), str) and isinstance(source.get('ref'), str) and type(location.get('offset')) is int


def _working_source(item):
    source = item.get('source')
    if not isinstance(source, dict) or not isinstance(source.get('ref'), str):
        return False
    return item.get('state') in ('current', 'saved-observation', 'stale', 'unavailable')


def _packet_location(item):
    source, location = item.get('source'), item.get('location')
    if not isinstance(source, dict) or not isinstance(location, dict):
        return False
    return isinstance(source.get('path'), str) and type(location.get('line')) is int


def _packet_contract(value):
    return (value.get('kind') == 'evidence-packet' and value.get('schemaVersion') == 1
            and isinstance(value.get('coverage'), dict) and isinstance(value.get('continuations'), list))


def _verify_state(value):
    state, code, session = value.get('executionState'), value.get('exitCode'), value.get('sessionId')
    if state == 'completed':
        return type(code) is int
    if state == 'running':
        return _verify_running(code, session)
    return state == 'unknown' and (code, session) == (None, None)


def _verify_running(code, session):
    return code is None and type(session) is int


def _verify_source(value):
    observations = value.get('observations')
    if observations is not None:
        return (isinstance(observations, list) and 1 <= len(observations) <= 9
                and all(_verify_observation(item) for item in observations))
    return _verify_reference(value)


def _verify_observation(value):
    return isinstance(value, dict) and isinstance(value.get('output', ''), str)


def _verify_reference(value):
    source = value.get('observationsRef')
    if not isinstance(source, dict) or source.get('path') != '/observations':
        return False
    ref = value.get('verificationRef')
    if not isinstance(ref, str) or re.fullmatch(r'ops://[a-f0-9]{48}', ref) is None:
        return False
    return source.get('ref') == ref


def _verify_diagnosis(value):
    diagnosis = value.get('diagnosis')
    if diagnosis is None:
        return True
    if not isinstance(diagnosis, dict) or diagnosis.get('operation') != 'diagnose':
        return False
    return _verify_diagnostic_rows(diagnosis.get('diagnostics'))


def _verify_diagnostic_rows(rows):
    return isinstance(rows, list) and all(_diagnostic(row) for row in rows)


def _verify(value):
    return (_packet(value) and _verify_state(value) and _verify_source(value)
            and _verify_diagnosis(value))


def _valid_payload(analysis):
    return (_workflow(analysis['value']) and _safe(analysis['metadata'])
            and _safe(analysis['value']))


def eligible(text, analysis):
    if len(text.encode('utf-8')) > _maximum(analysis):
        return False
    if not _valid_payload(analysis):
        return False
    try:
        original = json.loads(text)
    except (ValueError, RecursionError):
        return False
    return _transport(original) and _safe(original)


def _packet_candidate(analysis):
    value = analysis.get('value')
    return isinstance(value, dict) and _packet(value)


def _maximum(analysis):
    return PACKET_MAX_BYTES if _packet_candidate(analysis) else MAX_BYTES
