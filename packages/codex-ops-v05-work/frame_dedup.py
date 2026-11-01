"""Reuse exact emitted-text references only inside one outgoing result frame."""
import json

from presentation_policy import REFERENCE
from reducers import encode

MAX_ENTRIES = 16
MAX_SOURCE_BYTES = 2 * 1024 * 1024


def _reference(displayed):
    try:
        value = json.loads(displayed)
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict) or value.get('kind') != 'reference':
        return None
    return value if REFERENCE.fullmatch(str(value.get('ref', ''))) else None


def _repeat(receipt, block):
    return encode({'kind': 'reference', 'ref': receipt['ref'],
                   'sameAsTextBlock': block, 'repeatScope': 'same-result-frame',
                   'metadata': receipt.get('metadata', {}),
                   'retrieve': 'ops_result(ref, view="raw"); follow nextOffset'})


class FramePresenter:
    """A frame owns this instance; never retain it across responses or notifications."""
    def __init__(self, presenter):
        self.presenter = presenter
        self.entries = {}
        self.source_bytes = 0
        self.block = 0

    def _remember(self, text, displayed, size):
        if len(self.entries) >= MAX_ENTRIES or self.source_bytes + size > MAX_SOURCE_BYTES:
            return
        receipt = _reference(displayed)
        if receipt is None:
            return
        repeated = _repeat(receipt, self.block)
        if len(repeated.encode()) >= len(displayed.encode()):
            return
        self.entries[text] = repeated
        self.source_bytes += size

    def render(self, text, channel='text'):
        self.block += 1
        repeated = self.entries.get(text)
        if repeated is not None:
            self.presenter.record(channel, 'frame_repeat', len(text.encode()), len(repeated.encode()))
            return repeated
        displayed = self.presenter.render(text, channel)
        if displayed != text:
            self._remember(text, displayed, len(text.encode()))
        return displayed
