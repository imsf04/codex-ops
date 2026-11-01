"""Preserve actionable workflow evidence inside bounded observation receipts."""
from reducers import encode
import copy
import query_preview
from record_preview import preview as records
from workflow_diagnostics import FAILURE
import document_view

VERIFY_BYTES = 16000


def _row(label, value, pointer):
    return {'label': label, 'value': value, 'pointer': pointer}


def _diagnostics(value):
    return [_row('diagnostic', item, f'/diagnostics/{index}')
            for index, item in enumerate(value.get('diagnostics', []))]


def _documents(value):
    rows = [_row('document-status', document_view.outcome(item), f'/items/{index}')
            for index, item in enumerate(value.get('items', []))]
    for index, item in enumerate(value.get('items', [])):
        if 'result' in item:
            rows.append(_row('document', {'result': records(item['result'], 1200)}, f'/items/{index}/result'))
            continue
        for entry in item.get('evidence', {}).get('items', []):
            detail = {'resultRef': item['resultRef'], **entry}
            columns = item.get('evidence', {}).get('columns')
            if columns is not None:
                detail['columns'] = columns
            rows.append(_row('document', detail, f'/items/{index}/evidence'))
    return rows


def _incremental(value):
    rows = []
    for index, item in enumerate(value.get('items', [])):
        summary = {key: item.get(key) for key in ('path', 'mode', 'revision', 'sameFileRevision', 'omittedUnchangedLines')}
        rows.append(_row('file', summary, f'/items/{index}'))
        rows.extend(_row('change', change, f'/items/{index}/changes/{number}')
                    for number, change in enumerate(item.get('changes', [])))
    return rows


def _candidates(value, operation):
    functions = {'diagnose': _diagnostics, 'documents': _documents, 'incremental': _incremental}
    return functions.get(operation, lambda _: [])(value)


def _context(result, value, budget):
    context = records(value.get('context', {}), 1200)
    candidate = {**result, 'context': context}
    return candidate if context is not None and len(encode(candidate).encode()) <= budget else result


def preview(value, operation, budget=3500):
    result = {'kind': 'workflow-evidence', 'operation': operation, 'status': value.get('status'),
              'snapshotRef': value.get('snapshotRef'), 'evidence': [], 'contextPath': '/context',
              'nextAction': value.get('nextAction', 'Read selected fields from the saved workflow result'),
              'previewOnly': True}
    candidates = _candidates(value, operation)
    for row in candidates:
        if len(encode({**result, 'evidence': [*result['evidence'], row]}).encode()) > budget - 1400:
            break
        result['evidence'].append(row)
    result['omittedPreviewRows'] = len(candidates) - len(result['evidence'])
    return _context(result, value, budget)


def _direct(value, operation):
    if operation == 'sdk':
        return value.get('operation') == 'sdk'
    return operation in ('investigate', 'evidence', 'working_set') and value.get('kind') == 'evidence-packet'


def _verify_packet(value):
    packet = copy.deepcopy(value)
    packet.update(kind='evidence-packet', schemaVersion=1, evidenceState='collected',
                  items=[], continuations=[])
    packet['coverage'].update(observationsInline=True, diagnosisComplete=True,
                              deliveryOmittedDiagnostics=0)
    return packet


def _verify_large(packet):
    return len(encode(packet).encode('utf-8')) > VERIFY_BYTES


def _verify_reference(store, value, packet):
    receipt = store.capture(value, scope='verification-evidence', force=True)
    if receipt.get('kind') != 'reference':
        return False
    packet.pop('observations')
    packet['verificationRef'] = receipt['ref']
    packet['observationsRef'] = {'ref': receipt['ref'], 'path': '/observations'}
    packet['coverage']['observationsInline'] = False
    packet['continuations'] = [{'tool': 'ops_result', 'ref': receipt['ref'],
                                'view': 'raw', 'path': '/observations'}]
    return True


def _verify_diagnosis(packet):
    diagnosis = packet.get('diagnosis')
    if not isinstance(diagnosis, dict):
        return
    keys = ('status', 'effectState', 'operation', 'error', 'diagnostics', 'omittedDiagnostics',
            'sourceCompleteness')
    packet['diagnosis'] = {key: value for key, value in diagnosis.items() if key in keys}
    packet['coverage'].update(diagnosisComplete=False, diagnosisContextOmitted=True)
    packet['diagnosisRef'] = {'ref': packet['verificationRef'], 'path': '/diagnosis'}


def _verify_trim(packet):
    _verify_diagnosis(packet)
    diagnosis = packet.get('diagnosis') or {}
    rows = list(diagnosis.get('diagnostics', []))
    rows.sort(key=lambda row: (not bool(FAILURE.search(row.get('text', ''))), row.get('line', 0)))
    diagnosis['diagnostics'] = rows
    while _verify_large(packet) and rows:
        rows.pop()
        packet['coverage']['deliveryOmittedDiagnostics'] += 1


def _verify_capture(store, value):
    if value.get('operation') != 'verify' or value.get('status') != 'completed':
        return {'kind': 'inline', 'value': value}
    packet = _verify_packet(value)
    if not _verify_large(packet):
        return {'kind': 'inline', 'value': packet}
    if not _verify_reference(store, value, packet):
        return {'kind': 'inline', 'value': value}
    return _verify_finish(packet)


def _verify_finish(packet):
    if _verify_large(packet):
        _verify_trim(packet)
    return {'kind': 'inline', 'value': packet}


def capture(store, value, operation):
    if operation == 'verify':
        return _verify_capture(store, value)
    if _direct(value, operation):
        return {'kind': 'inline', 'value': value}
    if operation == 'locate':
        return query_preview.capture(store, value, 'search')
    receipt = store.capture(value)
    if receipt.get('kind') == 'reference':
        receipt['preview'] = preview(value, operation)
    return receipt
