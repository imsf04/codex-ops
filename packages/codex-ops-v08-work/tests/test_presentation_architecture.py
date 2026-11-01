import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experimental'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime_bridge'))
import presentation
import presentation_policy
from projection import project, SERVICE
from wire import fields, pack_varint, replace


def field(number, value):
    return pack_varint(number << 3 | 2) + pack_varint(len(value)) + value


class PresentationArchitectureTests(unittest.TestCase):
    def test_all_wire_value_types_preserve_bytes_and_reject_short_values(self):
        original = b'\x08\x96\x01' + b'\x11' + b'12345678' + b'\x1d' + b'abcd' + field(4, b'text')
        parsed = fields(original)
        self.assertEqual([x.value for x in parsed], [150, b'12345678', b'abcd', b'text'])
        self.assertEqual(replace(original, 4, lambda text: text), original)
        for value in (b'\x11short', b'\x1dx', b'\x22\x04x', b'\x0b', b'\x00'):
            with self.assertRaises(ValueError):
                fields(value)

    def test_ambiguous_execution_states_and_missing_identity_are_opaque(self):
        item = field(2, field(1, field(1, b'x' * 20000)))
        for body in (item + field(5, b''), field(1, b'id') + item + field(5, b'') + field(3, b''),
                     field(1, b'id') + item + b'\x28\x00'):
            original = field(2, body)
            self.assertEqual(project(SERVICE + 'Execute', original), original)

    def test_invalid_completed_shapes_and_non_text_content_keep_original_values(self):
        base = {'type': 'execute/initialResponse', 'result': {'status': 'ok', 'value': None}}
        for value in (None, {}, {'Result': None}, {'Result': {'content_items': 'invalid'}},
                      {'Result': {'error_text': 'failure', 'content_items': []}}):
            frame = copy.deepcopy(base)
            frame['result']['value'] = value
            self.assertIs(presentation.output(frame), frame)
        base['result']['value'] = {'Result': {'content_items': [None, {'type': 'future'}, {'type': 'input_text', 'text': 42}]}}
        self.assertEqual(presentation.output(base), base)
        for value in (None, {'type': 'future'}):
            frame = {'type': 'operation/response', 'result': {'status': 'ok', 'value': value}}
            self.assertIs(presentation.output(frame), frame)
        for frame in (None, 42, {'type': 'delegate/request', 'request': {'type': 'notification/send', 'text': 42}}):
            self.assertIs(presentation.output(frame), frame)

    def test_failed_or_oversized_capture_never_replaces_original_text(self):
        original = 'long text ' * 4000
        with patch.object(presentation_policy, 'Store', side_effect=OSError('unavailable')):
            self.assertEqual(presentation.compact(original), original)
        with patch.object(presentation_policy, 'Store') as factory:
            store = factory.return_value
            store.capture.return_value = {'kind': 'inline'}
            self.assertEqual(presentation.compact(original), original)
            store.close.assert_called_once()
            store.capture.return_value = {'kind': 'reference', 'metadata': {}, 'preview': original * 2}
            self.assertEqual(presentation.compact(original), original)
        self.assertEqual(presentation.compact('small'), 'small')
        self.assertIsNone(presentation.compact(None))


if __name__ == '__main__':
    unittest.main()
