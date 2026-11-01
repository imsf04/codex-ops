import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime_bridge'))
from frame_dedup import FramePresenter
from presentation_policy import Presenter
from projection import SERVICE, project
from store import Store
from wire import fields, pack_varint


def field(number, data):
    return pack_varint((number << 3) | 2) + pack_varint(len(data)) + data


def response(texts, envelope=2):
    content = b''.join(field(2, field(1, field(1, text.encode()))) for text in texts)
    return field(envelope, field(1, b'cell-1') + content + field(5, b''))


def text_blocks(frame):
    body = fields(fields(frame)[0].value)
    return [fields(fields(item.value)[0].value)[0].value.decode() for item in body if item.number == 2]


class FrameDedupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'CODEX_OPS_STORE': self.temp.name})
        self.env.start()
        self.raw = json.dumps({'status': 'completed', 'items': list(range(1500))})

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_repeated_values_share_one_exact_reference_in_same_response(self):
        for method, envelope in [('Execute', 2), ('Wait', 1)]:
            with self.subTest(method=method):
                events = []
                raw = response([self.raw, 'middle', self.raw], envelope)
                original = bytes(raw)
                result = project(SERVICE + method, raw, Presenter(observer=lambda *x: events.append(x)))
                first, middle, repeated = text_blocks(result)
                a, b = json.loads(first), json.loads(repeated)
                self.assertEqual(raw, original)
                self.assertEqual(middle, 'middle')
                self.assertEqual(a['ref'], b['ref'])
                self.assertEqual(b['sameAsTextBlock'], 1)
                self.assertEqual(b['repeatScope'], 'same-result-frame')
                self.assertEqual(a['metadata'], b['metadata'])
                self.assertLess(len(repeated), len(first))
                self.assertEqual(events[-1][0:2], (method.lower().replace('execute', 'text'), 'frame_repeat'))
                saved = Store()
                try:
                    self.assertEqual(saved.get(a['ref']), self.raw)
                finally:
                    saved.close()

    def test_exact_value_changes_and_response_boundaries_never_reuse(self):
        events = []
        presenter = Presenter(observer=lambda *x: events.append(x))
        first = text_blocks(project(SERVICE + 'Execute', response([self.raw, self.raw + ' ']), presenter))
        second = text_blocks(project(SERVICE + 'Execute', response([self.raw]), presenter))
        refs = [json.loads(x)['ref'] for x in first + second]
        self.assertNotEqual(refs[0], refs[1])
        self.assertEqual([x[1] for x in events], ['compacted'] * 3)
        self.assertTrue(all('sameAsTextBlock' not in json.loads(x) for x in first + second))

    def test_notify_is_excluded_even_when_two_values_share_one_frame(self):
        events = []
        raw = field(3, field(5, self.raw.encode()) + field(5, self.raw.encode()))
        result = project(SERVICE + 'OpenSession', raw, Presenter(observer=lambda *x: events.append(x)))
        blocks = [json.loads(x.value) for x in fields(fields(result)[0].value)]
        self.assertEqual([x[0:2] for x in events], [('notify', 'compacted')] * 2)
        self.assertTrue(all('sameAsTextBlock' not in x for x in blocks))

    def test_reference_inputs_and_storage_failure_never_become_repeat_proof(self):
        reference = json.dumps({'kind': 'reference', 'ref': 'ops://' + 'a' * 48})
        presenter = FramePresenter(Presenter())
        self.assertEqual(presenter.render(reference), reference)
        self.assertEqual(presenter.render(reference), reference)
        with patch('presentation_policy._capture', side_effect=OSError('offline')):
            self.assertEqual(presenter.render(self.raw), self.raw)
            self.assertEqual(presenter.render(self.raw), self.raw)
        self.assertEqual(presenter.entries, {})

    def test_invalid_or_unhelpful_receipts_are_not_reused(self):
        outputs = ['not json', '[]', '{}', '{"kind":"reference","ref":"invalid"}',
                   json.dumps({'kind': 'reference', 'ref': 'ops://' + 'a' * 48})]
        for output in outputs:
            with self.subTest(output=output):
                source = Mock()
                source.render.return_value = output
                presenter = FramePresenter(source)
                self.assertEqual(presenter.render(self.raw), output)
                self.assertEqual(presenter.render(self.raw), output)
                self.assertEqual(source.render.call_count, 2)
                source.record.assert_not_called()

    def test_entry_and_byte_budgets_retain_first_proof_without_growing(self):
        with patch('frame_dedup.MAX_ENTRIES', 1):
            presenter = FramePresenter(Presenter())
            first = presenter.render(self.raw)
            presenter.render(self.raw + ' ')
            self.assertEqual(len(presenter.entries), 1)
            self.assertEqual(presenter.source_bytes, len(self.raw.encode()))
            self.assertEqual(json.loads(first)['ref'], json.loads(presenter.render(self.raw))['ref'])
        with patch('frame_dedup.MAX_SOURCE_BYTES', 1):
            presenter = FramePresenter(Presenter())
            presenter.render(self.raw)
            self.assertEqual(presenter.entries, {})
            self.assertEqual(presenter.source_bytes, 0)


if __name__ == '__main__':
    unittest.main()
