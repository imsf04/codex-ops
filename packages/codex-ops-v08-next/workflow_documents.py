"""Extract evidence from bounded native document reads and preserve exact results."""
from reducers import encode
from workflow_validation import callback, complete, coverage, integer, options, require, text
import workflow_document_rows
import document_routing
import document_view

OPERATIONS = ('read', 'read_table', 'read_docx', 'read_pdf', 'inspect')
MAX_NODES = 4000
INLINE_BYTES = 4096


def _requests(args):
    requests = args.get('requests')
    require(isinstance(requests, list) and 1 <= len(requests) <= 4, 'documents requires 1..4 requests')
    for item in requests:
        require(isinstance(item, dict) and set(item) == {'operation', 'args'}, 'Each request requires operation and args')
        require(item['operation'] in OPERATIONS and isinstance(item['args'], dict), 'Unsupported document read operation or args')
    return requests


def _pointer(key):
    return str(key).replace('~', '~0').replace('/', '~1')


def _children(value):
    if isinstance(value, dict):
        return list(value.items())
    if isinstance(value, list):
        return list(enumerate(value))
    return []


def _preview(result, pointer, current, query, maximum):
    if len(result) < maximum:
        start = max(0, current.find(query) - 80)
        result.append({'pointer': pointer, 'text': current[start:start + 400],
                       'characterOffset': start, 'clipped': len(current) > 400})


def evidence(value, query, maximum):
    pending, result, visited, matches = [('', value)], [], 0, 0
    while pending and visited < MAX_NODES:
        pointer, current = pending.pop()
        visited += 1
        if isinstance(current, str) and query in current:
            matches += 1
            _preview(result, pointer, current, query, maximum)
        pending.extend((pointer + '/' + _pointer(key), child) for key, child in reversed(_children(current)))
    return {'items': result, 'matchedStrings': matches, 'scanComplete': not pending,
            'omittedMatches': matches - len(result), 'nodesScanned': visited}


def _stored(result, budget, save):
    size = len(encode(result).encode('utf-8'))
    if size <= budget['remaining']:
        budget['remaining'] -= size
        return {'result': result}
    return {'resultRef': save(result), 'sourceCoverage': coverage(result)}


def _matches(result, query, maximum, inline):
    found = evidence(result, query, maximum)
    if inline:
        found['items'] = [{'pointer': item['pointer']} for item in found['items']]
    else:
        found = workflow_document_rows.enrich(found, result)
    return found


def _item(index, request, result, query, maximum, save, budget):
    source_complete = complete(result)
    item = {'index': index, 'operation': request['operation'], 'status': result.get('status'),
            'sourceComplete': source_complete, **_stored(result, budget, save)}
    if result.get('error'):
        item['error'] = result['error']
    if query:
        found = _matches(result, query, maximum, 'result' in item)
        item.update(evidence=found, matchConclusion=_conclusion(found, source_complete))
    elif 'resultRef' in item:
        item['evidence'] = document_view.excerpts(result, maximum)
    return item


def _conclusion(found, source_complete):
    if found['matchedStrings']:
        return 'observed-string-matches'
    return 'absent-in-complete-response' if source_complete and found['scanComplete'] else 'unknown'


def _status(items, status):
    if status != 'completed':
        return status
    return 'completed' if all(_complete(item) for item in items) else 'partial'


def _complete(item):
    return item['sourceComplete'] and item.get('evidence', {}).get('scanComplete', True)


def run(root, args, invoke, save):
    options(args, ('requests', 'query', 'maxEvidence'))
    requested = _requests(args)
    requests, routes = document_routing.normalize(requested)
    query = text(args.get('query', ''), 'query', 512, empty=True)
    maximum = integer(args, 'maxEvidence', 1, 40, 8)
    writer = callback(save, 'save')
    result = invoke(root, 'batch', {'requests': requests})
    if 'items' not in result:
        return result
    budget = {'remaining': INLINE_BYTES}
    items = [_item(index, request, item['result'], query, maximum, writer, budget)
             for index, (request, item) in enumerate(zip(requests, result['items']))]
    for item, route in zip(items, routes):
        if route is not None:
            item['routing'] = route
    return {'status': _status(items, result['status']), 'effectState': 'none', 'operation': 'documents',
            'requestCount': len(requests), 'requestedCount': len(requested), 'items': items,
            'sourceCompleteness': 'per-result; literal case-sensitive matching over native response strings',
            'nextAction': 'Read inline result directly. resultRef retrieves absent content; follow native result/sourceCoverage cursors for unread source.'}
