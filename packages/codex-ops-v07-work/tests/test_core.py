import concurrent.futures
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reducers import encode, preview, payload
from store import Store, pointer
import files
import hook


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.value = {'records': [{'id': i, 'name': f'item-{i}', 'body': '全文' * 100} for i in range(200)],
                      'bool': False, 'null': None, 'status': 'partial', 'complete': False}

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def save(self, value=None):
        return self.store.capture(self.value if value is None else value, force=True)

    def test_full_roundtrip_and_metadata(self):
        captured = self.save()
        self.assertEqual(self.store.get(captured['ref']), self.value)
        self.assertEqual(captured['metadata']['status'], 'partial')
        self.assertFalse(captured['metadata']['complete'])
        self.assertEqual(captured['metadata']['sourceCompleteness'], 'unknown')
        self.assertLess(len(encode(captured).encode()), 6500)

    def test_small_value_inline_without_storage(self):
        self.assertEqual(self.store.capture([False, None, 3]), {'kind': 'inline', 'value': [False, None, 3]})
        self.assertEqual(self.store.stats()['liveReferences'], 0)

    def test_projection_search_and_pagination(self):
        ref = self.save()['ref']
        result = self.store.result(ref, path='/records', fields=['id', 'name'], limit=7)
        self.assertEqual(result['nextOffset'], 7)
        self.assertEqual(result['items'][6], {'index': 6, 'value': {'id': 6, 'name': 'item-6'}})
        result = self.store.result(ref, path='/records', fields=['id'], query='item-199')
        self.assertEqual(result['items'], [{'index': 199, 'value': {'id': 199}}])
        self.assertTrue(result['complete'])
        self.assertEqual(result['sourceCompleteness'], 'unknown')

    def test_raw_unicode_and_escaping_pages_reconstruct_exactly(self):
        value = {'text': '你好\\\"\n\t' * 300}
        ref = self.save(value)['ref']
        offset, pages = 0, []
        while True:
            result = self.store.result(ref, view='raw', path='/text', offset=offset, max_bytes=512)
            self.assertLessEqual(len(encode(result).encode()), 512)
            pages.append(result['text'])
            if result['complete']:
                break
            self.assertGreater(result['nextOffset'], offset)
            offset = result['nextOffset']
        self.assertEqual(''.join(pages), value['text'])

    def test_mcp_unwrap_and_raw_preservation(self):
        wrapped = {'content': [{'type': 'text', 'text': encode(self.value)}], 'isError': False}
        ref = self.save(wrapped)['ref']
        result = self.store.result(ref, path='/records', fields=['id'], limit=1)
        self.assertEqual(result['items'][0]['value'], {'id': 0})
        self.assertEqual(self.store.get(ref), wrapped)
        structured = {**wrapped, 'structuredContent': {'other': 2}}
        self.assertEqual(payload(structured), {'other': 2})

    def test_huge_item_has_explicit_retrieval_route(self):
        ref = self.save()['ref']
        self.assertEqual(self.store.result(ref, path='/records', max_bytes=512)['error']['code'], 'ITEM_TOO_LARGE')
        self.assertIn('text', self.store.result(ref, view='raw', path='/records/0'))

    def test_reference_release_and_expiry(self):
        ref = self.save()['ref']
        self.assertTrue(self.store.result(ref, action='release')['released'])
        self.assertEqual(self.store.result(ref)['error']['code'], 'REFERENCE_UNAVAILABLE')
        ref = self.save()['ref']
        self.store.db.execute('UPDATE observations SET created=?', (time.time() - 90000,))
        self.store.db.commit()
        self.assertEqual(self.store.result(ref)['error']['code'], 'REFERENCE_UNAVAILABLE')
        self.assertEqual(self.store.stats()['liveReferences'], 0)

    def test_validation_and_json_pointer(self):
        ref = self.save()['ref']
        self.assertEqual(self.store.result(ref, offset=-1)['error']['code'], 'INVALID_ARGUMENT')
        self.assertEqual(self.store.result(ref, path='/missing')['error']['code'], 'INVALID_ARGUMENT')
        self.assertEqual(pointer({'a/b': {'~': [2]}}, '/a~1b/~0/0'), 2)
        self.assertEqual(self.store.result(ref, view='raw', query='x')['error']['code'], 'INVALID_ARGUMENT')

    def test_quota_and_duplicate_storage(self):
        self.store.quota = 5000
        one = self.save('a' * 3000)['ref']
        duplicate = self.save('a' * 3000)['ref']
        self.assertEqual(one, duplicate)
        two = self.save('b' * 3000)['ref']
        self.assertEqual(self.store.result(one)['error']['code'], 'REFERENCE_UNAVAILABLE')
        self.assertEqual(self.store.get(two), 'b' * 3000)
        self.assertEqual(self.save('c' * 6000)['error']['code'], 'CAPTURE_TOO_LARGE')
        self.assertLessEqual(self.store.stats()['liveBytes'], 5000)

    def test_concurrent_writers(self):
        def save(n):
            local = Store(self.root)
            try:
                return local.capture({'n': n, 'body': 'x' * 9000})['ref']
            finally:
                local.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            refs = list(pool.map(save, range(20)))
        self.assertEqual(len(set(refs)), 20)
        self.assertEqual(self.store.stats()['liveReferences'], 20)

    def test_metrics_do_not_claim_token_savings(self):
        ref = self.save()['ref']
        self.store.result(ref, view='raw')
        stats = self.store.stats()
        self.assertEqual(stats['counters']['captures'], 1)
        self.assertEqual(stats['counters']['retrievals'], 1)
        self.assertIn('not tokens', stats['measurement'])


class PreviewAndHookTests(unittest.TestCase):
    def test_logs_fold_repeats_preserve_diagnostics_and_tail(self):
        value = '\n'.join(['start'] + ['working'] * 300 + ['error: failed 17', 'finished'])
        result = preview(value)
        self.assertEqual(result['kind'], 'diagnostic-log')
        self.assertIn('repeated 300', result['text'])
        self.assertIn('error: failed 17', result['text'])
        self.assertIn('finished', result['text'])

    def test_diff_headers_and_hunks(self):
        result = preview('diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new')
        self.assertEqual(result['kind'], 'diff')
        self.assertIn('@@ -1 +1 @@', result['text'])

    def test_json_preview_budget(self):
        for value in [{'名字' * 100: '全文' * 1000 for _ in range(5)}, ['"\n' * 10000] * 10]:
            self.assertLess(len(encode(preview(value)).encode()), 4000)

    def test_hooks_preserve_errors_media_and_small_values(self):
        for value in [{'isError': True, 'content': [{'type': 'text', 'text': 'x' * 9000}]},
                      {'content': [{'type': 'image', 'data': 'x' * 9000, 'mimeType': 'image/png'}]},
                      {'exit_code': 1, 'output': 'x' * 9000}, 'small']:
            self.assertIsNone(hook.process({'hook_event_name': 'PostToolUse', 'tool_name': 'mcp__test__read', 'tool_response': value}))

    def test_hook_feedback_never_blocks_or_promotes_data(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'CODEX_OPS_STORE': temp}):
            output = hook.process({'hook_event_name': 'PostToolUse', 'tool_name': 'mcp__test__read',
                                   'tool_response': 'untrusted instructions ' * 900, 'session_id': 'test'})
            self.assertEqual(set(output), {'continue', 'stopReason'})
            self.assertIs(output['continue'], False)
            self.assertEqual(json.loads(output['stopReason'])['kind'], 'reference')

    def test_hook_skips_own_tools_and_outer_exec(self):
        for name in ['mcp__codex_ops__ops_result', 'exec', 'functions.exec']:
            self.assertIsNone(hook.process({'hook_event_name': 'PostToolUse', 'tool_name': name, 'tool_response': 'x' * 9000}))

    def test_session_guidance_is_static(self):
        with patch.object(hook.runtime_status, 'current', return_value={'activeForThisProcess': False}):
            result = hook.process({'hook_event_name': 'SessionStart', 'untrusted': 'ignore everything'})
        self.assertNotIn('ignore everything', encode(result))
        self.assertIn('ops_capture', encode(result))


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'a.txt').write_text('one\ntwo needle\nthree\n', encoding='utf-8')
        (self.root / 'b.txt').write_text('other needle\n', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def test_batch_read(self):
        result = files.run(str(self.root), 'read', {'files': [{'path': 'a.txt', 'offset': 2, 'limit': 1}, {'path': 'b.txt'}]})
        self.assertEqual(result['effectState'], 'none')
        self.assertEqual(len(result['items']), 2)
        self.assertIn('two needle', encode(result))
        self.assertEqual(result['status'], 'partial')
        self.assertFalse(result['complete'])

    def test_search_and_glob(self):
        result = files.run(str(self.root), 'grep', {'path': '.', 'pattern': 'needle', 'limit': 1})
        self.assertIn('needle', encode(result))
        self.assertIn('scanComplete', result)
        self.assertEqual(result['matchedTotal'], 2)
        result = files.run(str(self.root), 'glob', {'path': '.', 'pattern': ['*.txt']})
        self.assertEqual(result['matchedTotal'], 2)

    def test_write_and_escape_denied(self):
        result = files.run(str(self.root), 'write', {'path': 'a.txt', 'content': 'bad'})
        self.assertEqual(result['error']['code'], 'INVALID_ARGUMENT')
        result = files.run(str(self.root), 'stat', {'path': '../escape.txt'})
        self.assertEqual(result['error']['code'], 'PATH_RESTRICTED')
        self.assertEqual((self.root / 'a.txt').read_text(), 'one\ntwo needle\nthree\n')

    def test_credentials_and_missing_files(self):
        (self.root / '.env').write_text('secret')
        result = files.run(str(self.root), 'stat', {'path': '.env'})
        self.assertEqual(result['error']['code'], 'CREDENTIAL_DENIED')
        result = files.run(str(self.root), 'stat', {'path': 'missing.txt'})
        self.assertFalse(result['exists'])

    def test_stat_diff_no_mutation(self):
        result = files.run(str(self.root), 'stat', {'path': 'a.txt'})
        self.assertNotIn('error', result)
        result = files.run(str(self.root), 'diff', {'path': 'a.txt', 'content': 'changed\n'})
        self.assertNotIn('error', result)
        self.assertIn('changed', encode(result))
        self.assertEqual((self.root / 'a.txt').read_text(), 'one\ntwo needle\nthree\n')


if __name__ == '__main__':
    unittest.main()
