"""Observed workflow executions; task opportunity eligibility remains unknown."""
from collections import Counter
import json
import document_view


def _item(record):
    payload = record.get('payload', {})
    if payload.get('type') != 'item_completed':
        return None
    item = payload.get('item', {})
    if item.get('type') == 'McpToolCall' and item.get('tool') == 'ops_workflow':
        return item
    return None


def _result(item):
    result = item.get('result') or {}
    if result.get('isError'):
        return {'status': 'error'}
    return _unwrap(_raw_value(result))


def _raw_value(result):
    value = result.get('structuredContent')
    if value is None:
        value = _text_value(result.get('content') or [])
    return value


def _unwrap(value):
    value = _object(value)
    if value.get('kind') == 'inline':
        return _object(value.get('value'))
    return value


def _object(value):
    return value if isinstance(value, dict) else {}


def _text_value(content):
    if len(content) != 1 or content[0].get('type') != 'text':
        return {}
    try:
        return json.loads(content[0].get('text', ''))
    except (ValueError, TypeError):
        return {}


def _outcome(item):
    if item.get('error') or item.get('status') in ('failed', 'cancelled', 'interrupted'):
        return 'failed'
    if _result(item).get('status') in ('error', 'failed', 'rejected'):
        return 'failed'
    return 'completed' if item.get('status') == 'completed' else 'unknown'


def summarize(records):
    seen, outcomes, operations, evidence = set(), Counter(), Counter(), Counter()
    for record in records:
        item = _item(record)
        if item is not None:
            _count(item, seen, outcomes, operations, evidence)
    return {'selected': sum(outcomes.values()), 'completed': outcomes['completed'],
            'failed': outcomes['failed'], 'unknown': outcomes['unknown'],
            'byOperation': dict(operations), 'evidence': dict(evidence), 'eligible': None, 'adoptionRate': None,
            'reason': 'Observed native completion records only; eligible task opportunities are not labelled. Completion does not prove useful evidence or task success.'}


def _count(item, seen, outcomes, operations, evidence):
    key = item.get('id')
    if key is None or key in seen:
        return
    seen.add(key)
    outcomes[_outcome(item)] += 1
    operations[operation(item)] += 1
    evidence[assess(_result(item))['evidence']] += 1


def operation(item):
    arguments = item.get('arguments') or {}
    if arguments.get('operation') is not None:
        return arguments['operation']
    return 'investigate' if 'question' in arguments else 'unknown'


def assess(value):
    value = _unwrap(value)
    status = value.get('status', 'unknown')
    outcome = 'failed' if status in ('error', 'failed', 'rejected') else status
    return {'outcome': outcome, 'evidence': _evidence(value),
            'reused': _object(value.get('evidenceReuse')).get('hit') is True}


def _evidence(value):
    if value.get('evidenceState') in ('no_match', 'needs_anchor'):
        return 'absent'
    if value.get('evidenceState') == 'collected' and _has_rows(value.get('items', [])):
        return 'present'
    return _operation_evidence(value)


def _operation_evidence(value):
    if value.get('operation') == 'working_set':
        return _working_set_evidence(value)
    if value.get('operation') == 'documents':
        return _documents_evidence(value)
    if value.get('operation') == 'verify':
        return 'present' if type(value.get('exitCode')) is int else 'unknown'
    if value.get('diagnostics'):
        return 'present'
    return 'unknown'


def _working_set_evidence(value):
    return 'present' if any(_has_rows(_working_rows(item)) for item in value.get('items', [])) else 'unknown'


def _working_rows(item):
    if item.get('state') in ('current', 'saved-observation'):
        return _object(item.get('result')).get('items', [])
    if item.get('state') == 'stale':
        return _fresh_rows(item)
    return []


def _fresh_rows(item):
    if item.get('currentEvidenceOmitted'):
        return []
    evidence = _object(item.get('currentEvidence'))
    revision = evidence.get('revision')
    if not isinstance(revision, str) or not revision or revision != item.get('currentRevision') or revision == item.get('revision'):
        return []
    return evidence.get('items', [])


def _documents_evidence(value):
    rows = [row for item in value.get('items', []) for row in document_view.evidence(item)]
    return 'present' if _has_rows(rows) else 'absent'


def _has_rows(rows):
    return any(_row_content(row) for row in rows)


def _row_content(row):
    if isinstance(row.get('text'), str) and row['text'].strip():
        return True
    return bool(row.get('row'))
