"""Extract evidence from bounded native document reads and preserve exact results."""
from workflow_validation import callback, complete, coverage, integer, options, require, text

OPERATIONS = ('read', 'read_table', 'read_docx', 'read_pdf', 'inspect')
MAX_NODES = 4000


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


def _item(index, request, result, query, maximum, save):
    found = evidence(result, query, maximum)
    source_complete = complete(result)
    return {'index': index, 'operation': request['operation'], 'status': result.get('status'),
            'resultRef': save(result), 'evidence': found, 'sourceCoverage': coverage(result),
            'sourceComplete': source_complete, 'matchConclusion': _conclusion(found, source_complete)}


def _conclusion(found, source_complete):
    if found['matchedStrings']:
        return 'observed-string-matches'
    return 'absent-in-complete-response' if source_complete and found['scanComplete'] else 'unknown'


def _status(items, status):
    if status != 'completed':
        return status
    return 'completed' if all(item['sourceComplete'] and item['evidence']['scanComplete'] for item in items) else 'partial'


def run(root, args, invoke, save):
    options(args, ('requests', 'query', 'maxEvidence'))
    requests = _requests(args)
    query = text(args.get('query', ''), 'query', 512, empty=True)
    maximum = integer(args, 'maxEvidence', 1, 40, 8)
    writer = callback(save, 'save')
    result = invoke(root, 'batch', {'requests': requests})
    if 'items' not in result:
        return result
    items = [_item(index, request, item['result'], query, maximum, writer)
             for index, (request, item) in enumerate(zip(requests, result['items']))]
    return {'status': _status(items, result['status']), 'effectState': 'none', 'operation': 'documents',
            'requestCount': len(requests), 'items': items,
            'sourceCompleteness': 'per-result; literal evidence search covers saved response strings',
            'nextAction': 'Use resultRef with the evidence JSON pointer for exact content; inspect scanComplete and source status.'}
