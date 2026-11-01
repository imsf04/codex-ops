"""Presentation policy: preserve raw observations, summarize only emitted text."""
import re
import json

from progress import Progress
from reducers import encode
from store import Store, THRESHOLD
from structured import analyze

REFERENCE = re.compile(r'ops://[a-f0-9]{48}')


def _result_page(value):
    if value.get('view') not in ('raw', 'items', 'outline', 'find'):
        return False
    field = 'text' if value['view'] == 'raw' else 'items'
    return field in value and 'nextOffset' in value and 'complete' in value


def _reference_kind(value):
    if not isinstance(value, dict):
        return None
    if not REFERENCE.fullmatch(str(value.get('ref', ''))):
        return None
    if value.get('kind') == 'reference':
        return 'already_compact'
    return 'explicit_retrieval' if _result_page(value) else None


def _threshold(analysis, progress):
    if progress is not None:
        return 256
    if analysis['kind'] in ('shell', 'json'):
        return 2048
    return THRESHOLD


def _bypass(analysis, progress, size):
    reference = _reference_kind(analysis['value'])
    limit = 65536 if reference == 'explicit_retrieval' else 20000
    if reference and size <= limit:
        return reference
    if size < _threshold(analysis, progress):
        return 'below_threshold'
    return None


def _capture(text):
    store = Store()
    try:
        return store.capture(text, scope='code-mode-presentation', force=True)
    finally:
        store.close()


def _receipt(receipt, progress):
    if progress is not None:
        return encode({'ref': receipt['ref'], **progress})
    receipt['metadata']['observationScope'] = 'emitted-text'
    receipt['retrieve'] = 'ops_result(ref, view="raw"); follow nextOffset to reconstruct exact emitted text'
    return encode(receipt)


def _render(text, progress):
    receipt = _capture(text)
    if receipt.get('kind') != 'reference':
        return text, 'storage_limit'
    displayed = _receipt(receipt, progress)
    if len(displayed.encode()) >= len(text.encode()):
        return text, 'not_beneficial'
    return displayed, 'progress_unchanged' if progress is not None else 'compacted'


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

    def _display(self, text, progress):
        try:
            return _render(text, progress)
        except Exception:
            return text, 'storage_unavailable'

    def render(self, text, channel='text'):
        if not isinstance(text, str):
            return text
        try:
            return self._render_text(text, channel)
        except Exception:
            size = len(text.encode(errors='replace'))
            self.record(channel, 'other', size, size)
            return text

    def _render_text(self, text, channel):
        analysis = analyze(text)
        progress = self.progress.observe(analysis)
        size = len(text.encode())
        reason = _bypass(analysis, progress, size)
        if reason:
            self.record(channel, reason, size, size)
            return text
        displayed, reason = self._display(text, progress)
        if reason in ('compacted', 'progress_unchanged'):
            self._link(displayed)
        self.record(channel, reason, size, len(displayed.encode()))
        return displayed
