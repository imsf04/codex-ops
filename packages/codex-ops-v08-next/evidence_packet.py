"""Exact source lines and explicit coverage in one bounded display contract."""
from reducers import encode
from store import error
import evidence_selection


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
    value = {'phase': stage['phase'], 'path': stage['args']['path'], 'status': result.get('status'),
            'role': stage.get('role', 'source'),
            'error': result.get('error'),
            'search': evidence_selection.coverage(result.get('search', result)),
            'context': evidence_selection.context(result.get('context', {})),
            'omittedMatches': result.get('omittedMatches', 0), 'omittedRanges': result.get('omittedRanges', 0)}
    if stage.get('searchAttempts'):
        value['searchAttempts'] = stage['searchAttempts']
        value['anchorOrigin'] = stage.get('anchorOrigin', 'explicit')
    return value


def _select(packet, rows, maximum):
    for row in rows:
        packet['items'].append(row)
        if len(encode(packet).encode('utf-8')) > maximum:
            packet['items'].pop()
            continue
    packet['coverage']['omittedEvidenceLines'] = len(rows) - len(packet['items'])
    return packet


def _unfilled(stages):
    return list(dict.fromkeys(stage['role'] for stage in stages
                if stage.get('role') in ('tests', 'configuration') and not list(source_lines(stage['result']))))


def build(query, stages):
    rows = evidence_selection.prioritized(_unique(stages), query['anchors'])
    state = 'collected' if rows else 'no_match'
    packet = {'kind': 'evidence-packet', 'schemaVersion': 1, 'operation': 'investigate',
              'status': 'completed', 'operationStatus': 'completed', 'effectState': 'none',
              'evidenceState': state, 'anchors': query['anchors'], 'focus': query['focus'], 'items': [],
              'coverage': {'stages': [_stage_coverage(stage) for stage in stages],
                           'unfilledRequestedRoles': _unfilled(stages),
                           'omittedEvidenceLines': len(rows), 'snapshotConsistency': 'non-atomic',
                           'meaning': 'Exact selected source lines; not a semantic answer or complete call graph.'},
              'continuations': evidence_selection.continuations(stages),
              'nextAction': 'Use cited evidence; follow continuations only for missing source coverage.'}
    if 'kernel' in query:
        packet['coverage']['kernel'] = query['kernel']
    _select(packet, rows, query['maxBytes'])
    if _partial(packet, stages):
        packet.update(status='partial', operationStatus='partial')
    return _bounded(packet, query['maxBytes'])


def _partial(packet, stages):
    omitted = packet['coverage'].get('kernel', {}).get('omittedStages', 0)
    gaps = packet['coverage']['unfilledRequestedRoles']
    return bool(omitted or gaps or packet['coverage']['omittedEvidenceLines']) or any(stage['result'].get('status') != 'completed' for stage in stages)


def _bounded(packet, maximum):
    if len(encode(packet).encode('utf-8')) > maximum:
        return error('EVIDENCE_BUDGET', 'Coverage metadata exceeds budget; use fewer paths or a larger maxBytes')
    return packet


def needs_anchor(query):
    return {'kind': 'evidence-packet', 'schemaVersion': 1, 'operation': 'investigate',
            'status': 'completed', 'operationStatus': 'completed', 'effectState': 'none',
            'evidenceState': 'needs_anchor', 'items': [], 'coverage': {'searched': False},
            'continuations': [], 'nextAction': 'Supply one exact code symbol, filename or repository phrase in anchors.'}
