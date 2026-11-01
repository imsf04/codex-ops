"""Observed workflow executions; task opportunity eligibility remains unknown."""
from collections import Counter
import json


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
    if _result(item).get('status') in ('error', 'failed'):
        return 'failed'
    return 'completed' if item.get('status') == 'completed' else 'unknown'


def summarize(records):
    seen, outcomes, operations = set(), Counter(), Counter()
    for record in records:
        item = _item(record)
        if item is not None:
            _count(item, seen, outcomes, operations)
    return {'selected': sum(outcomes.values()), 'completed': outcomes['completed'],
            'failed': outcomes['failed'], 'unknown': outcomes['unknown'],
            'byOperation': dict(operations), 'eligible': None, 'adoptionRate': None,
            'reason': 'Observed native completion records only; eligible task opportunities are not labelled. Completion does not prove useful evidence or task success.'}


def _count(item, seen, outcomes, operations):
    key = item.get('id')
    if key is None or key in seen:
        return
    seen.add(key)
    outcomes[_outcome(item)] += 1
    operations[(item.get('arguments') or {}).get('operation', 'unknown')] += 1
