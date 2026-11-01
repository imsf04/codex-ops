import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime_bridge'))
from projection import SERVICE, project
from wire import fields, pack_varint, replace


def field(number, data):
    return pack_varint((number << 3) | 2) + pack_varint(len(data)) + data


class GrpcProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'CODEX_OPS_STORE': self.temp.name})
        self.env.start()
        self.text = '完整结果' * 5000
        self.item = field(1, field(1, self.text.encode()))
        self.body = field(1, b'cell-1') + field(2, self.item) + field(5, b'')
        self.response = field(2, self.body)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_success_compacts_only_text(self):
        compacted = project(SERVICE + 'Execute', self.response)
        self.assertLess(len(compacted), len(self.response) // 5)
        body = fields(fields(compacted)[0].value)
        self.assertEqual(body[0].raw, field(1, b'cell-1'))
        self.assertEqual(body[-1].raw, field(5, b''))
        self.assertIn(b'ops://', compacted)

    def test_yield_and_wait(self):
        body = field(1, b'cell-1') + field(2, self.item) + field(3, b'')
        for method, envelope in [('Execute', field(2, body)), ('Wait', field(1, body))]:
            self.assertIn(b'ops://', project(SERVICE + method, envelope))

    def test_error_and_unknown_status_preserve_every_byte(self):
        for status in [field(5, field(8, b'unknown error schema')), field(4, b''), field(9, b'new status')]:
            original = field(2, field(1, b'cell-1') + field(2, self.item) + status)
            self.assertEqual(project(SERVICE + 'Execute', original), original)

    def test_failure_logs_compact_but_error_state_stays_byte_identical(self):
        status = field(5, field(1, b'original error with full stack'))
        original = field(2, field(1, b'cell-1') + field(2, self.item) + status)
        displayed = project(SERVICE + 'Execute', original)
        self.assertIn(b'ops://', displayed)
        self.assertEqual(fields(fields(displayed)[0].value)[-1].raw, status)

    def test_future_error_shapes_and_invalid_error_encoding_stay_opaque(self):
        statuses = [field(3, field(1, b'future')), field(5, field(1, b'a') + field(2, b'b')),
                    field(5, b'\x08\x01'), field(5, field(1, b'\xff'))]
        for status in statuses:
            raw = field(2, field(1, b'cell') + field(2, self.item) + status)
            self.assertEqual(project(SERVICE + 'Execute', raw), raw)

    def test_text_telemetry_excludes_control_bytes_and_preserves_error_measurement(self):
        from presentation_policy import Presenter
        calls = []
        presenter = Presenter(observer=lambda *args: calls.append(args))
        status = field(5, field(1, b'original failure'))
        raw = field(2, field(1, b'cell') + field(2, self.item) + status)
        project(SERVICE + 'CompleteToolCall', raw, presenter)
        self.assertEqual(calls, [])
        project(SERVICE + 'Execute', raw, presenter)
        self.assertEqual(calls[0], ('error', 'error_preserved', 16, 16))
        self.assertEqual(calls[1][0:2], ('text', 'compacted'))
        self.assertEqual(calls[1][2], len(self.text.encode()))

    def test_media_and_unknown_fields_stay_byte_identical(self):
        media = field(2, b'opaque-image-data')
        unknown = field(100, b'future-extension')
        original = field(2, field(1, b'cell-1') + field(2, media) + field(2, self.item) + unknown + field(5, b''))
        changed = project(SERVICE + 'Execute', original)
        self.assertIn(field(2, media), changed)
        self.assertIn(unknown, changed)
        self.assertIn(b'ops://', changed)

    def test_tool_calls_results_and_unknown_methods_never_transform(self):
        for method in ['CompleteToolCall', 'SubscribeToToolCalls', 'Terminate', 'Shutdown', 'Future']:
            self.assertEqual(project(SERVICE + method, self.response), self.response)

    def test_notifications_preserve_identifiers(self):
        notification = b''.join(field(n, b'identity') for n in range(1, 5)) + field(5, self.text.encode())
        changed = project(SERVICE + 'OpenSession', field(3, notification))
        values = fields(fields(changed)[0].value)
        self.assertEqual([x.value for x in values[:4]], [b'identity'] * 4)
        self.assertIn(b'ops://', values[-1].value)

    def test_malformed_frames_fail_open(self):
        for raw in [b'\x80', b'\x00', b'\x12\xff', b'\x13invalid', b'\x12\x05x']:
            self.assertEqual(project(SERVICE + 'Execute', raw), raw)

    def test_wire_passthrough_preserves_noncanonical_encoding(self):
        raw = b'\x88\x00\x81\x00' + field(2, b'unchanged')
        self.assertEqual(replace(raw, 2, lambda value: value), raw)


if __name__ == '__main__':
    unittest.main()
