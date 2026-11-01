"""Exact source lines and explicit coverage in one bounded display contract."""
from reducers import encode
from workflow_validation import coverage
from store import error


def source_lines(result):
    for item in result.get('context', {}).get('items', []):
        for line in item.get('items', []):
            if isinstance(line.get('text'), str) and type(line.get('line')) is int:
                yield {'kind': 'source-line', 'text': line['text'],
                       'source': {'path': line.get('path', item.get('path')), 'revision': item.get('revision')},
                       'location': {'line': line['line']}}


def _unique(stages):
    found = {}
    for stage in stages:
        for row in source_lines(stage['result']):
            key = (row['source']['path'], row['location']['line'], row['text'])
            found.setdefault(key, row)
    return list(found.values())


def _stage_coverage(stage):
    result = stage['result']
    return {'phase': stage['phase'], 'path': stage['args']['path'], 'status': result.get('status'),
            'search': coverage(result.get('search', result)), 'context': coverage(result.get('context', {})),
            'omittedMatches': result.get('omittedMatches', 0), 'omittedRanges': result.get('omittedRanges', 0)}


def _continuation(stage):
    return {'tool': 'ops_workflow', 'operation': 'locate', 'args': dict(stage['args']),
            'reason': 'Revisit this exact bounded range before paging; packet selection may omit its lines.'}


def _select(packet, rows, maximum):
    for row in rows:
        packet['items'].append(row)
        if len(encode(packet).encode('utf-8')) > maximum:
            packet['items'].pop()
            break
    packet['coverage']['omittedEvidenceLines'] = len(rows) - len(packet['items'])
    return packet


def build(query, stages):
    rows = _unique(stages)
    state = 'collected' if rows else 'no_match'
    packet = {'kind': 'evidence-packet', 'schemaVersion': 1, 'operation': 'investigate',
              'status': 'completed', 'operationStatus': 'completed', 'effectState': 'none',
              'evidenceState': state, 'anchors': query['anchors'], 'focus': query['focus'], 'items': [],
              'coverage': {'stages': [_stage_coverage(stage) for stage in stages],
                           'omittedEvidenceLines': len(rows), 'snapshotConsistency': 'non-atomic',
                           'meaning': 'Exact selected source lines; not a semantic answer or complete call graph.'},
              'continuations': [_continuation(stage) for stage in stages],
              'nextAction': 'Use cited evidence; follow continuations only for missing source coverage.'}
    _select(packet, rows, query['maxBytes'])
    if _partial(packet, stages):
        packet.update(status='partial', operationStatus='partial')
    return _bounded(packet, query['maxBytes'])


def _partial(packet, stages):
    return bool(packet['coverage']['omittedEvidenceLines']) or any(stage['result'].get('status') != 'completed' for stage in stages)


def _bounded(packet, maximum):
    if len(encode(packet).encode('utf-8')) > maximum:
        return error('EVIDENCE_BUDGET', 'Coverage metadata exceeds budget; use fewer paths or a larger maxBytes')
    return packet


def needs_anchor(query):
    return {'kind': 'evidence-packet', 'schemaVersion': 1, 'operation': 'investigate',
            'status': 'completed', 'operationStatus': 'completed', 'effectState': 'none',
            'evidenceState': 'needs_anchor', 'items': [], 'coverage': {'searched': False},
            'continuations': [], 'nextAction': 'Supply one exact code symbol, filename or repository phrase in anchors.'}
