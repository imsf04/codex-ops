"""Model-only workflow projection with exact original-text recovery."""
import json

from reducers import encode
import document_view
import diagnostic_view
import evidence_selection
import workflow_inline

MAXIMUM = 12000


def _shape(text, analysis):
    value = analysis.get('value')
    if not isinstance(value, dict) or analysis.get('metadata', {}).get('isError'):
        return False
    if not workflow_inline._workflow(value):
        return False
    try:
        return workflow_inline._transport(json.loads(text))
    except (ValueError, RecursionError):
        return False


def _base(value):
    fields = ('operation', 'status', 'effectState', 'evidenceState', 'executionState', 'exitCode',
              'sessionId', 'observationsRef', 'verificationRef')
    return {'kind': 'workflow-view', **{key: value[key] for key in fields if key in value}}


def _memory(value, view):
    reused = value.get('evidenceReuse', {})
    if reused.get('hit'):
        view['reuse'] = {'hit': True, 'revisionsChecked': reused.get('revisionsChecked'), 'contextRetentionAssumed': False}
    if value.get('workingSet', {}).get('state') == 'saved':
        view['workingSet'] = {'state': 'saved', 'availableForLater': True}
    if value.get('operation') == 'working_set':
        view['pending'] = value.get('pending', [])
        view['pendingMeaning'] = 'Caller-provided notes, not independently verified facts'


def _coverage(value):
    coverage = value.get('coverage', {})
    fields = ('omittedEvidenceLines', 'snapshotConsistency', 'observations', 'sourceComplete',
              'diagnosisComplete', 'deliveryOmittedDiagnostics', 'searched')
    result = {key: coverage[key] for key in fields if key in coverage}
    if 'kernel' in coverage:
        result['kernel'] = _kernel(coverage['kernel'])
    stages = coverage.get('stages', [])
    if stages:
        result['stages'] = [{'role': stage.get('role', 'source'), 'status': stage.get('status'),
                             'error': stage.get('error'), 'scanComplete': stage.get('search', {}).get('scanComplete')}
                            for stage in stages]
    return result


def _kernel(value):
    return {key: value[key] for key in ('plannedStages', 'omittedStages', 'pendingStages') if key in value}


def _source_rows(items, view):
    sources, rows = [], []
    for item in items:
        rows.extend(_item_rows(item, _source_id(sources, item.get('source'))))
        rows.extend(_fresh_rows(item, sources, view))
    return sources, rows


def _source_id(sources, source):
    if source not in sources:
        sources.append(source)
    return sources.index(source) + 1


def _item_rows(item, source):
    row = {'source': source, **item.get('location', {}),
           **{key: item[key] for key in ('text', 'state', 'kind', 'error', 'reason', 'contentOmitted',
                                        'currentRevision', 'currentEvidenceOmitted') if key in item}}
    if item.get('kind') != 'working-source':
        return [row]
    if item.get('state') not in ('current', 'saved-observation'):
        return [row]
    return _working_rows(item.get('result'), row)


def _working_rows(value, row):
    if isinstance(value, str):
        return [{**row, 'text': value}]
    excerpts = document_view.excerpts(value, maximum=4000, text_limit=None)['items']
    if excerpts:
        return [{**row, **excerpt} for excerpt in excerpts]
    return [{**row, 'value': value}]


def _fresh_rows(item, sources, view):
    if item.get('state') != 'stale':
        return []
    if item.get('currentEvidenceOmitted'):
        return _fresh_reference(item, sources, view)
    current = item.get('currentEvidence')
    if not _current_source(current) or current['revision'] != item.get('currentRevision'):
        return []
    source = _fresh_source(current, sources, view)
    return _fresh_lines(current['items'], source)


def _fresh_lines(items, source):
    return [_fresh_line(row, source) for row in items if _source_line(row)]


def _current_source(value):
    if not isinstance(value, dict) or value.get('status') not in ('completed', 'partial'):
        return False
    return _source_identity(value) and isinstance(value.get('items'), list)


def _source_identity(value):
    if not isinstance(value, dict):
        return False
    return all(isinstance(value.get(key), str) and value[key] for key in ('path', 'revision'))


def _fresh_source(value, sources, view):
    source = _source_id(sources, {key: value[key] for key in ('path', 'revision')})
    fields = ('status', 'complete', 'truncated', 'nextOffset', 'omitted', 'failed', 'requestedWindow', 'coverageMeaning')
    view.setdefault('currentReads', []).append({'source': source, **{key: value[key] for key in fields if key in value}})
    return source


def _source_line(value):
    return isinstance(value, dict) and type(value.get('line')) is int and isinstance(value.get('text'), str)


def _fresh_line(value, source):
    result = {'source': source, 'state': 'current-read', 'line': value['line'], 'text': value['text']}
    if value.get('truncatedInLine'):
        result['clipped'] = True
    return result


def _fresh_reference(item, sources, view):
    current = item.get('currentRead', {})
    if not _source_identity(current) or current['revision'] != item.get('currentRevision'):
        return []
    source = _fresh_source(current, sources, view)
    row = {'source': source, 'state': 'current-read', 'contentOmitted': True}
    if item.get('currentEvidenceRef'):
        row['ref'] = item['currentEvidenceRef']
    return [row]


def _rows(value, view):
    if value['operation'] == 'documents':
        view['documents'] = document_view.summary(value)
        return [{'document': item['index'], **row} for item in value['items'] for row in document_view.evidence(item)]
    if value['operation'] in ('verify', 'diagnose'):
        diagnosis = value.get('diagnosis') or value
        return diagnostic_view.rows(diagnosis, view)
    sources, rows = _source_rows(value.get('items', []), view)
    view['sources'] = sources
    return rows


def _bounded_row(row, maximum):
    result = dict(row)
    content = result.get('text')
    if isinstance(content, str) and len(encode(result).encode()) > maximum:
        result.update(text=_prefix(result, maximum), clipped=True)
    return result


def _prefix(row, maximum):
    content = row['text']
    low, high = 0, len(content)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = {**row, 'text': content[:middle], 'clipped': True}
        if len(encode(candidate).encode()) <= maximum:
            low = middle
        else:
            high = middle - 1
    return content[:low]


def _fit(view, rows, budget):
    view['evidence'] = []
    allowance = max(80, budget - len(encode(view).encode()) - 500)
    per_row = _row_budget(rows, allowance)
    for row in rows:
        candidate = _bounded_row(row, per_row)
        if len(encode({**view, 'evidence': [*view['evidence'], candidate]}).encode()) > budget - 350:
            break
        view['evidence'].append(candidate)
    view['omittedDisplayRows'] = len(rows) - len(view['evidence'])
    diagnostic_view.finish(view, rows)
    return view


def _row_budget(rows, allowance):
    if sum(len(encode(row).encode()) for row in rows) <= allowance:
        return allowance
    return max(80, allowance // max(1, len(rows)) - 80)


def project(value, budget=MAXIMUM):
    view = _base(value)
    _memory(value, view)
    view['coverage'] = _coverage(value)
    rows = _rows(value, view)
    if value.get('evidenceState') == 'needs_anchor':
        view['nextAction'] = value.get('nextAction')
    return _fit(view, rows, max(768, budget))


def render(text, analysis, budget, capture):
    if len(text.encode()) < 2048 or not _shape(text, analysis):
        return None
    maximum = budget or MAXIMUM
    view = project(analysis['value'], maximum)
    size = len(encode(view).encode()) + 180
    if size > min(len(text.encode()) * 0.8, maximum):
        return None
    receipt = capture(text)
    if receipt.get('kind') != 'reference':
        return None
    view.update(ref=receipt['ref'], retrieve='ops_result(ref, view="raw") for exact original; follow nextOffset')
    return encode(view)
