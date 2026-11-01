"""Validate and retrieve a bounded set of cached queries in one tool request."""
import re
from reducers import encode
from store import error
import observation_metrics

KEYS = frozenset(('ref', 'view', 'path', 'fields', 'query', 'offset', 'limit', 'max_bytes'))
VIEWS = frozenset(('items', 'raw', 'outline', 'find', 'count', 'group'))


def _request(value):
    if not isinstance(value, dict) or set(value) - KEYS:
        raise ValueError('Each query requires ref and supported page options; mutations are unavailable')
    if not re.fullmatch(r'ops://[a-f0-9]{48}', str(value.get('ref', ''))):
        raise ValueError('Every query requires an ops reference')
    if value.get('view', 'items') not in VIEWS:
        raise ValueError('Unknown query view; use items/raw/outline/find/count/group')
    _options(value)
    return dict(value)


def _integer(value, key, low, high=None):
    if key not in value:
        return
    number = value[key]
    if type(number) is not int or number < low:
        raise ValueError(key + ' must be an integer within its page bounds')
    if high is not None and number > high:
        raise ValueError(key + ' exceeds its page bound')


def _text(value, key, maximum):
    if key not in value:
        return
    if not isinstance(value[key], str) or len(value[key]) > maximum:
        raise ValueError(key + ' must be a bounded string')


def _field_name(value):
    return isinstance(value, str) and len(value) <= 256


def _fields(value):
    if value is None:
        return
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError('fields must be a list of up to 32 names')
    if any(not _field_name(item) for item in value):
        raise ValueError('Each field name must be a string of at most 256 characters')


def _options(value):
    _integer(value, 'offset', 0)
    _integer(value, 'limit', 1, None if value.get('view') == 'raw' else 200)
    _integer(value, 'max_bytes', 512, 16000)
    _text(value, 'path', 2048)
    _text(value, 'query', 200)
    _fields(value.get('fields'))


def _validated(requests, max_bytes):
    if not isinstance(requests, list) or not 1 <= len(requests) <= 8:
        raise ValueError('Batch accepts 1..8 independent cached queries')
    if not 512 <= max_bytes <= 16000:
        raise ValueError('Batch max_bytes must be 512..16000')
    if len(encode(requests).encode()) > 32768:
        raise ValueError('Batch request exceeds 32 KiB; shorten paths and filters')
    return [_request(item) for item in requests], _budget(len(requests), max_bytes)


def _budget(count, max_bytes):
    budget = (max_bytes - 256 - count * 48) // count
    if budget < 512:
        raise ValueError('Increase max_bytes or reduce queries to allow 512 bytes per result')
    return budget


def _retrieve(store, request, budget):
    request['max_bytes'] = min(request.get('max_bytes', budget), budget)
    return store.result(**request)


def _measure(items, requests):
    for item, request in zip(items, requests):
        defaults = [('view', 'items'), ('path', ''), ('fields', None), ('query', ''),
                    ('offset', 0), ('limit', 40), ('max_bytes', 6000)]
        options = [request.get(key, default) for key, default in defaults] + ['page']
        observation_metrics.retrieval(item['result'], options)


def run(store, requests, max_bytes):
    try:
        requests, budget = _validated(requests, max_bytes)
        items = [{'index': index, 'result': _retrieve(store, request, budget)}
                 for index, request in enumerate(requests)]
        result = {'kind': 'result-batch', 'items': items, 'requestCount': len(requests),
                  'complete': True, 'sourceCompleteness': 'per-result'}
        if len(encode(result).encode()) > max_bytes:
            return error('BATCH_BUDGET_EXCEEDED', 'Increase max_bytes or shorten paths; no source operation ran')
        _measure(items, requests)
        return result
    except (ValueError, TypeError) as exc:
        return error('INVALID_ARGUMENT', str(exc))
