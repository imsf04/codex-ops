"""Structured previews retain native facts without modifying stored observations."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reducers import encode, metadata, payload, preview
from store import Store
from structured import analyze, MAX_JSON_BYTES


class StructuredPreviewTests(unittest.TestCase):
    def test_serialized_records_have_counts_and_fields_instead_of_escaped_text(self):
        original = json.dumps({'records': [{'id': i, 'name': '记录 ' + str(i)} for i in range(400)],
                               'complete': False, 'nextOffset': 400}, ensure_ascii=False)
        result = preview(original)
        self.assertEqual(result['kind'], 'json')
        self.assertEqual(result['sample']['records']['itemCount'], 400)
        self.assertEqual(result['sample']['records']['sample'][0]['id'], 0)
        self.assertNotIn('previewText', result)
        self.assertEqual(metadata(original)['nextOffset'], 400)
        self.assertFalse(metadata(original)['complete'])
        self.assertLessEqual(len(encode(result).encode()), 3500)

    def test_native_shell_failure_keeps_code_session_diagnostic_and_tail(self):
        lines = ['build starting'] + ['uninteresting line ' + str(i) for i in range(300)]
        lines[101] = 'ERROR: compile failed in module alpha'
        lines.append('FINAL_FAILURE_SENTINEL')
        original = json.dumps({'exit_code': 7, 'session_id': 12345, 'output': '\n'.join(lines),
                               'status': 'failed', 'truncated': False})
        analyzed = analyze(original)
        self.assertEqual(analyzed['kind'], 'shell')
        result = preview(original)
        self.assertEqual((result['exit_code'], result['session_id'], result['status']), (7, 12345, 'failed'))
        self.assertIn('ERROR: compile failed', result['text'])
        self.assertIn('FINAL_FAILURE_SENTINEL', result['text'])
        self.assertLessEqual(len(encode(result).encode()), 3500)

    def test_json_stdout_keeps_native_state_and_record_counts(self):
        value = {'exit_code': 0, 'output': json.dumps([{'path': 'file-' + str(i)} for i in range(200)])}
        result = preview(json.dumps(value))
        self.assertEqual(result['kind'], 'json')
        self.assertEqual(result['exit_code'], 0)
        self.assertEqual(result['sample']['itemCount'], 200)
        self.assertEqual(result['sample']['sample'][0]['path'], 'file-0')
        self.assertLessEqual(len(encode(result).encode()), 3500)

    def test_mcp_envelopes_keep_outer_authority_and_nested_failure_information(self):
        value = {'isError': False, 'status': 'completed', 'content': [{'type': 'text', 'text': 'unused'}],
                 'structuredContent': {'status': 'error', 'exit_code': 7, 'error': {'message': 'failed'}, 'output': 'trace'}}
        original = copy.deepcopy(value)
        result = analyze(json.dumps(value))
        self.assertEqual(value, original)
        self.assertEqual(result['metadata']['status'], 'completed')
        self.assertEqual(result['metadata']['exit_code'], 7)
        self.assertEqual(result['metadata']['payloadMetadata'][0]['status'], 'error')
        self.assertEqual(result['value'], value['structuredContent'])

    def test_three_steps_include_terminal_state_but_do_not_unwrap_fourth(self):
        shell = {'output': 'done', 'exit_code': 0}
        three = json.dumps({'content': [{'type': 'text', 'text': json.dumps(shell)}]})
        self.assertEqual(analyze(three)['metadata']['exit_code'], 0)
        nested = {'structuredContent': {'structuredContent': {'structuredContent': {'structuredContent': shell}}}}
        result = analyze(nested)
        self.assertEqual(result['value'], {'structuredContent': shell})
        self.assertNotIn('exit_code', result['metadata'])

    def test_plain_scalars_invalid_and_oversized_json_remain_text(self):
        for value in ('false', 'null', '123', '"hello"', 'not JSON', '{broken'):
            self.assertEqual(payload(value), value)
            self.assertEqual(analyze(value)['kind'], 'text')
        large = json.dumps({'body': 'x' * MAX_JSON_BYTES})
        self.assertEqual(payload(large), large)
        multibyte = json.dumps({'body': '界' * (MAX_JSON_BYTES // 2)}, ensure_ascii=False)
        self.assertEqual(payload(multibyte), multibyte)
        with patch('structured.json.loads', side_effect=RecursionError('decoder limit')):
            self.assertEqual(payload('[nested]'), '[nested]')

    def test_mcp_scalar_blocks_and_unknown_media_keep_their_contract(self):
        self.assertEqual(payload({'content': [{'type': 'text', 'text': 'false'}, {'type': 'text'},
                                              {'type': 'text', 'text': 3}]}), [False, '', 3])
        self.assertIsNone(payload({'content': [{'type': 'text', 'text': 'null'}]}))
        for value in ({'content': [None]}, {'content': [{'type': 'image', 'data': 'raw'}]},
                      {'content': []}, {'structuredContent': 1}, 42, None):
            self.assertEqual(payload(value), value)

    def test_saved_serialized_text_roundtrips_exactly_and_items_can_project(self):
        original = '  ' + json.dumps({'records': [{'id': i, 'body': '界' * 150} for i in range(100)]},
                                     ensure_ascii=False, indent=2) + '\n'
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            try:
                receipt = store.capture(original)
                self.assertEqual(store.get(receipt['ref']), original)
                self.assertEqual(receipt['preview']['kind'], 'json')
                page = store.result(receipt['ref'], path='/records', fields=['id'], limit=2)
                self.assertEqual(page['items'][1]['value'], {'id': 1})
                offset, restored = 0, ''
                while True:
                    part = store.result(receipt['ref'], view='raw', offset=offset, max_bytes=16000)
                    restored += part['text']
                    if part['complete']:
                        break
                    offset = part['nextOffset']
                self.assertEqual(restored, original)
            finally:
                store.close()

    def test_preview_budget_stays_structured_for_large_nested_json_and_escaped_logs(self):
        nested = {'field' + str(i): [{'large': ['x' * 300] * 10} for _ in range(10)] for i in range(12)}
        result = preview(json.dumps(nested), budget=600)
        self.assertEqual(result['kind'], 'json')
        self.assertTrue(result['clipped'])
        self.assertNotIn('previewText', result)
        self.assertLessEqual(len(encode(result).encode()), 600)
        enormous_keys = {'\x01' * 300: 42}
        result = preview(enormous_keys, budget=512)
        self.assertEqual(result, {'kind': 'json', 'valueType': 'dict', 'clipped': True})
        log = {'output': '\x01' * 2000 + '\nERROR: escaped diagnostic\nTAIL', 'exit_code': 7}
        result = preview(log, budget=600)
        self.assertLessEqual(len(encode(result).encode()), 600)
        self.assertIn('TAIL', result['text'])
        self.assertEqual(result['exit_code'], 7)

    def test_metadata_marks_large_values_clipped_without_mutating_input(self):
        value = {'status': 'error', 'error': 'error' * 1000, 'coverage': {'total': 42}, 'exit_code': 7}
        original = copy.deepcopy(value)
        result = metadata(json.dumps(value))
        self.assertTrue(result['error']['clipped'])
        self.assertEqual(result['coverage'], {'total': 42})
        self.assertEqual(value, original)

    def test_escaped_wire_budget_keeps_diagnostic_separate_from_clipped_log(self):
        lines = [str(i) + ': ' + '\x01' * 120 for i in range(15)]
        lines[7] = 'ERROR: important compilation failure'
        lines.append('LAST_LINE')
        result = preview({'output': '\n'.join(lines), 'exit_code': 7})
        self.assertTrue(result['clipped'])
        self.assertIn('ERROR: important compilation failure', result['diagnostics'])
        self.assertIn('LAST_LINE', result['text'])
        self.assertEqual(result['exit_code'], 7)
        self.assertLessEqual(len(encode(result).encode()), 3500)
        limited = preview({'output': '\n'.join('error ' + str(i) for i in range(10))})
        self.assertEqual(limited['diagnostics'], ['error 0', 'error 1', 'error 2'])

    def test_unrepresentable_preview_marks_clipping_instead_of_returning_invalid_json(self):
        result = preview({'output': '', 'session_id': 'x' * 5000}, budget=512)
        self.assertEqual(result, {'kind': 'text', 'clipped': True})


if __name__ == '__main__':
    unittest.main()
