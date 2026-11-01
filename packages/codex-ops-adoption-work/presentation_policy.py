"""Presentation policy: preserve raw observations, summarize only emitted text."""
import re
import json

from progress import Progress
from reducers import encode, preview as bounded_preview
from store import Store, THRESHOLD
from structured import analyze
from semantic_preview import preview as semantic_preview
from evidence_preview import preview as evidence_preview
from workflow_inline import eligible as workflow_inline

REFERENCE = re.compile(r'ops://[a-f0-9]{48}')


def _result_page(value):
    if value.get('view') not in ('raw', 'items', 'outline', 'find', 'count', 'group'):
        return False
    field = 'text' if value['view'] == 'raw' else 'items'
    return field in value and 'nextOffset' in value and 'complete' in value


def _batch_header(value):
    if value.get('kind') != 'result-batch' or value.get('complete') is not True:
        return False
    count = value.get('requestCount')
    return type(count) is int and 1 <= count <= 8


def _batch_item(row, index):
    if not isinstance(row, dict) or row.get('index') != index:
        return False
    result = row.get('result')
    if not isinstance(result, dict):
        return False
    if result.get('status') == 'error' and isinstance(result.get('error'), dict):
        return True
    return _referenced_page(result)


def _referenced_page(value):
    return bool(REFERENCE.fullmatch(str(value.get('ref', '')))) and _result_page(value)


def _result_batch(value):
    if not _batch_header(value):
        return False
    items = value.get('items')
    if not isinstance(items, list) or len(items) != value['requestCount']:
        return False
    return all(_batch_item(row, index) for index, row in enumerate(items))


def _reference_kind(value):
    if not isinstance(value, dict):
        return None
    if _result_batch(value):
        return 'explicit_retrieval'
    if not REFERENCE.fullmatch(str(value.get('ref', ''))):
        return None
    if value.get('kind') == 'reference':
        return 'already_compact'
    return 'explicit_retrieval' if _result_page(value) else None


def _threshold(analysis, progress):
    if progress is not None:
        return 256
    if analysis.get('semanticPreview') is not None:
        return 768
    if analysis.get('workflowInline'):
        return 8193
    if analysis['kind'] in ('shell', 'json'):
        return 2048
    return THRESHOLD


def _bypass(analysis, progress, size, budget=None):
    reference = _reference_kind(analysis['value'])
    limit = 65536 if reference == 'explicit_retrieval' else 20000
    if reference and size <= limit:
        return reference
    if _over_budget(size, budget):
        return None
    if size < _threshold(analysis, progress):
        return 'below_threshold'
    return None


def _over_budget(size, budget):
    return budget is not None and size > max(768, budget)


def _capture(text):
    store = Store()
    try:
        return store.capture(text, scope='code-mode-presentation', force=True)
    finally:
        store.close()


def _receipt(receipt, progress, summary=None):
    if progress is not None:
        return encode({'ref': receipt['ref'], **progress})
    if summary is not None:
        return encode({'kind': 'reference', 'ref': receipt['ref'], 'metadata': receipt['metadata'],
                       'preview': summary, 'retrieve': 'ops_result(ref, view="raw")'})
    receipt['metadata']['observationScope'] = 'emitted-text'
    receipt['retrieve'] = 'ops_result(ref, view="raw"); follow nextOffset to reconstruct exact emitted text'
    return encode(receipt)


def _budget_receipt(receipt, text, budget):
    return encode({'kind': 'reference', 'ref': receipt['ref'],
        'metadata': receipt['metadata'], 'preview': bounded_preview(text, max(160, budget - 550)),
        'frameBudget': {'targetBytes': budget, 'scope': 'same-result-frame', 'soft': True},
        'retrieve': 'ops_result(ref, view="raw"); follow nextOffset'})


def _fit_receipt(receipt, text, displayed, budget):
    if budget is None or len(displayed.encode()) <= budget:
        return displayed
    bounded = _budget_receipt(receipt, text, budget)
    return bounded if len(bounded.encode()) < len(displayed.encode()) else displayed


def _render(text, progress, summary=None, budget=None):
    receipt = _capture(text)
    if receipt.get('kind') != 'reference':
        return text, 'storage_limit'
    displayed = _fit_receipt(receipt, text, _receipt(receipt, progress, summary), budget)
    if not _beneficial(text, displayed, summary):
        return text, 'not_beneficial'
    return displayed, 'progress_unchanged' if progress is not None else 'compacted'


def _beneficial(original, displayed, summary):
    before, after = len(original.encode()), len(displayed.encode())
    if summary is not None:
        return before - after >= 128 and after <= before * 0.8
    return after < before


class Presenter:
    def __init__(self, observer=None, progress=None, on_reference=None):
        self.observer = observer
        self.progress = progress if progress is not None else Progress()
        self.on_reference = on_reference

    def _link(self, displayed):
        if self.on_reference is None:
            return
        try:
            self.on_reference(json.loads(displayed)['ref'])
        except Exception:
            pass

    def record(self, channel, reason, before, after):
        if self.observer is None:
            return
        try:
            self.observer(channel, reason, before, after)
        except Exception:
            pass  # Measurement never prevents a source result from reaching the host.

    def _display(self, text, progress, summary=None, budget=None):
        try:
            return _render(text, progress, summary, budget)
        except Exception:
            return text, 'storage_unavailable'

    def render_budgeted(self, text, channel, budget):
        return self.render(text, channel, budget)

    def render(self, text, channel='text', budget=None):
        if not isinstance(text, str):
            return text
        try:
            return self._render_text(text, channel, budget)
        except Exception:
            size = len(text.encode(errors='replace'))
            self.record(channel, 'other', size, size)
            return text

    def _render_text(self, text, channel, budget=None):
        analysis = analyze(text)
        analysis['workflowInline'] = workflow_inline(text, analysis)
        analysis['semanticPreview'] = semantic_preview(analysis) or evidence_preview(analysis)
        progress = self.progress.observe(analysis)
        size = len(text.encode())
        reason = _bypass(analysis, progress, size, budget)
        if reason:
            self.record(channel, reason, size, size)
            return text
        displayed, reason = self._display(text, progress, analysis['semanticPreview'], budget)
        if reason in ('compacted', 'progress_unchanged'):
            self._link(displayed)
        self.record(channel, reason, size, len(displayed.encode()))
        return displayed
