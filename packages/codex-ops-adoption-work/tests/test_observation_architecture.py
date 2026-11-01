"""Retrieval, presentation and native-worker contracts through their interfaces."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import files
from reducers import encode, payload, preview, small, text_preview
from store import Store, pointer


class RetrievalContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def save(self, value):
        return self.store.capture(value, force=True)['ref']

    def test_invalid_options_do_not_count_as_successful_retrievals(self):
        ref = self.save({'items': ['one', 'two']})
        bad = [{'action': 'mutate'}, {'view': 'summary'}, {'offset': -1}, {'limit': 0},
               {'limit': 201}, {'max_bytes': 511}, {'max_bytes': 16001},
               {'view': 'raw', 'fields': ['items']}, {'path': 'items'},
               {'path': '/items/no-number'}, {'path': '/items/99'}, {'path': '/items', 'fields': ['id']}]
        for options in bad:
            with self.subTest(options=options):
                result = self.store.result(ref, **options)
                self.assertEqual(result['error']['code'], 'INVALID_ARGUMENT')
        self.assertNotIn('retrievals', self.store.stats()['counters'])
        self.assertEqual(self.store.get(ref), {'items': ['one', 'two']})

    def test_budget_stops_after_last_whole_record_and_resumes(self):
        data = [{'id': n, 'text': 'x' * 100} for n in range(4)]
        ref = self.save(data)
        first = self.store.result(ref, max_bytes=700)
        self.assertTrue(first['items'])
        self.assertFalse(first['complete'])
        second = self.store.result(ref, offset=first['nextOffset'], max_bytes=700)
        self.assertEqual([r['value'] for r in first['items'] + second['items']], data)
        self.assertTrue(second['complete'])
        self.assertLessEqual(len(encode(first).encode()), 700)

    def test_empty_matches_scalars_and_offsets_keep_cursor_meaning(self):
        ref = self.save('first\nsecond\nlast')
        match = self.store.result(ref, query='last')
        self.assertEqual(match['items'], [{'index': 2, 'value': 'last'}])
        self.assertEqual((match['sourceItems'], match['matchedItems']), (3, 1))
        self.assertEqual(self.store.result(ref, query='missing')['items'], [])
        self.assertIsNone(self.store.result(ref, offset=20)['nextOffset'])
        scalar = self.save(False)
        self.assertEqual(self.store.result(scalar)['items'], [{'index': 0, 'value': False}])
        self.assertEqual(self.store.result(scalar, view='raw')['text'], 'false')
        self.assertEqual(self.store.result(ref, view='raw', offset=999)['text'], '')

    def test_projection_omits_absent_keys_and_never_mutates_saved_value(self):
        data = [{'id': 1, 'name': '全文'}, {'id': 2, 'name': 'last'}]
        ref = self.save(data)
        result = self.store.result(ref, fields=['id', 'missing'], query='last')
        self.assertEqual(result['items'], [{'index': 1, 'value': {'id': 2}}])
        self.assertEqual(self.store.get(ref), data)
        self.assertFalse(self.store.result('ops://missing', action='release')['released'])

    def test_pointer_escaping_and_numeric_mapping_keys_differ_from_array_indices(self):
        value = {'a/b': {'~x': [False]}, '0': 'mapping-key'}
        self.assertIs(pointer(value, ''), value)
        self.assertIs(pointer(value, '/a~1b/~0x/0'), False)
        self.assertEqual(pointer(value, '/0'), 'mapping-key')
        with self.assertRaises(ValueError):
            pointer(value, 'not-a-pointer')


class PreviewContractTests(unittest.TestCase):
    def test_mcp_text_formats_media_and_structured_precedence(self):
        wrapper = {'content': [{'type': 'text', 'text': 'false'}, {'type': 'text', 'text': 'plain'}, {'type': 'text'}]}
        self.assertEqual(payload(wrapper), [False, 'plain', ''])
        self.assertEqual(payload({'content': [{'type': 'text', 'text': 'null'}]}), None)
        self.assertEqual(payload({**wrapper, 'structuredContent': [3]}), [3])
        for value in [{'content': []}, {'content': 'invalid'}, {'content': [{'type': 'image'}]}, 'plain']:
            self.assertEqual(payload(value), value)

    def test_deep_json_samples_stop_recursing_and_prefer_identity_fields(self):
        value = {'other': {'a': {'b': {'deep': True}}}, 'id': 7, 'list': [[[[False]]]], 'long': '界' * 100}
        result = small(value)
        self.assertEqual(next(iter(result)), 'id')
        self.assertEqual(result['other']['a']['b'], {'keys': ['deep'], 'keyCount': 1})
        self.assertEqual(result['list']['sample'][0]['sample'][0], {'itemCount': 1})
        self.assertEqual(result['long']['bytes'], 300)
        self.assertEqual(small('short'), 'short')
        self.assertEqual(small(False), False)

    def test_diagnostic_selection_is_bounded_and_keeps_tail(self):
        lines = ['start'] + [f'warning {n}' for n in range(40)] + ['last line']
        result = text_preview('\n'.join(lines), 3500)
        self.assertEqual(result['selectedLines'], 24)
        self.assertIn('42: last line', result['text'])
        self.assertEqual(result['kind'], 'diagnostic-log')
        self.assertEqual(text_preview('', 100)['selectedLines'], 0)
        clipped = text_preview('界' * 200, 100)
        self.assertIn('[line clipped]', clipped['text'])
        self.assertLessEqual(len(clipped['text'].encode()), 100)
        self.assertEqual(preview({'output': 'hello'})['kind'], 'text')


class WorkerContractTests(unittest.TestCase):
    def test_native_request_preserves_lexical_path_and_input_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'sub').mkdir()
            args = {'files': [{'path': 'sub/../document.txt'}]}
            response = subprocess.CompletedProcess([], 0, stdout=b'{"status":"completed"}')
            with patch('files.subprocess.run', return_value=response) as invoke:
                self.assertEqual(files.run(str(root), 'read', args), {'status': 'completed'})
            envelope = json.loads(invoke.call_args.kwargs['input'])
            self.assertEqual(envelope['request']['args']['files'][0]['path'], str(root / 'sub/../document.txt'))
            self.assertEqual(args, {'files': [{'path': 'sub/../document.txt'}]})
            self.assertTrue(envelope['request']['read_only'])
            self.assertTrue(envelope['request']['deny_credential_names'])

    def test_worker_errors_do_not_become_successes_or_change_files(self):
        with tempfile.TemporaryDirectory() as folder:
            for failure, code in [(subprocess.TimeoutExpired('worker', 32), 'WORKER_TIMEOUT'),
                                  (OSError('unavailable'), 'WORKER_ERROR')]:
                with self.subTest(code=code), patch('files.subprocess.run', side_effect=failure):
                    self.assertEqual(files.run(folder, 'stat', {})['error']['code'], code)
            for result, code in [(subprocess.CompletedProcess([], 5, stdout=b''), 'WORKER_FAILED'),
                                 (subprocess.CompletedProcess([], 0, stdout=b'not-json'), 'WORKER_ERROR')]:
                with self.subTest(code=code), patch('files.subprocess.run', return_value=result):
                    self.assertEqual(files.run(folder, 'stat', {})['error']['code'], code)
            self.assertEqual(files.run(folder, 'stat', {'path': None})['error']['code'], 'INVALID_ARGUMENT')
            self.assertEqual(files.run('.', 'stat', {})['error']['code'], 'INVALID_ARGUMENT')
            self.assertEqual(files.run(str(Path(folder) / 'missing'), 'stat', {})['error']['code'], 'INVALID_ARGUMENT')


if __name__ == '__main__':
    unittest.main()
