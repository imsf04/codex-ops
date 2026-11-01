import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experimental'))
from presentation import output


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'CODEX_OPS_STORE': self.temp.name})
        self.env.start()
        self.frame = {'type': 'execute/initialResponse', 'id': 2, 'result': {'status': 'ok', 'value': {
            'Result': {'cell_id': '1', 'content_items': [{'type': 'input_text', 'text': 'x' * 20000}],
                       'error_text': None, 'code_mode_host_duration_ns': 123}}}}

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_buffered_text_compacted_without_mutating_frame_or_metadata(self):
        original = copy.deepcopy(self.frame)
        projected = output(self.frame)
        self.assertEqual(self.frame, original)
        body = projected['result']['value']['Result']
        self.assertEqual(body['cell_id'], '1')
        self.assertEqual(body['code_mode_host_duration_ns'], 123)
        self.assertIsNone(body['error_text'])
        self.assertTrue(json.loads(body['content_items'][0]['text'])['ref'].startswith('ops://'))

    def test_delegate_tool_values_and_controls_are_unchanged(self):
        for frame in [
            {'type': 'delegate/response', 'id': 1, 'result': {'status': 'ok', 'value': {'type': 'tool/result', 'result': 'x' * 20000}}},
            {'type': 'delegate/request', 'request': {'type': 'tool/invoke', 'invocation': {'input': 'x' * 20000}}},
            {'type': 'operation/cancel', 'id': 2}, {'type': 'operation/yield', 'id': 2},
            {'type': 'cell/closed', 'sessionId': 's', 'cellId': '1'}]:
            self.assertIs(output(frame), frame)

    def test_media_keeps_order_and_payload(self):
        image = {'type': 'input_image', 'image_url': 'data:image/png;base64,EXAMPLE', 'detail': 'original'}
        items = self.frame['result']['value']['Result']['content_items']
        items.insert(0, image)
        items.append({'type': 'input_audio', 'data': 'EXAMPLE'})
        projected = output(self.frame)['result']['value']['Result']['content_items']
        self.assertEqual(projected[0], image)
        self.assertEqual(projected[2], items[2])

    def test_script_errors_pass_through_with_diagnostics(self):
        self.frame['result']['value']['Result']['error_text'] = 'Error: original failure'
        self.assertIs(output(self.frame), self.frame)

    def test_notifications_keep_callback_identity(self):
        frame = {'type': 'delegate/request', 'id': 3, 'sessionId': 's', 'request': {
            'type': 'notification/send', 'callId': 'call', 'cellId': '1', 'text': 'large' * 4000}}
        result = output(frame)
        self.assertEqual(result['id'], 3)
        self.assertEqual(result['sessionId'], 's')
        self.assertEqual(result['request']['callId'], 'call')
        self.assertIn('ops://', result['request']['text'])

    def test_wait_and_yield_outputs(self):
        value = self.frame['result']['value']
        for variant in ['Result', 'Yielded']:
            state = {variant: value['Result']}
            frame = {'type': 'operation/response', 'id': 4, 'result': {'status': 'ok', 'value': {
                'type': 'wait/completed', 'outcome': {'LiveCell': state}}}}
            result = output(frame)
            text = result['result']['value']['outcome']['LiveCell'][variant]['content_items'][0]['text']
            self.assertIn('ops://', text)

    def test_unknown_future_protocol_and_small_messages_unchanged(self):
        for frame in [{'type': 'future/output', 'text': 'x' * 20000}, {'type': 'operation/response', 'result': {'status': 'error', 'message': 'x' * 20000}}]:
            self.assertEqual(output(frame), frame)
        self.frame['result']['value']['Result']['content_items'][0]['text'] = 'small'
        self.assertEqual(output(self.frame), self.frame)


if __name__ == '__main__':
    unittest.main()
