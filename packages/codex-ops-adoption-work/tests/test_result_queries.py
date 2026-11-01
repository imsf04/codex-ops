import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import query_aggregates
import result_batch
import server
import files
from store import Store
from reducers import encode
from telemetry import snapshot


class ResultQueriesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'CODEX_OPS_STORE': self.temp.name})
        self.env.start()
        self.store = Store()
        self.value = [{'status': 'ok', 'id': 1}, {'status': 'fail', 'id': 2},
                      {'status': 'ok', 'id': 3}, {'other': 'missing'}, {'status': None}]
        self.ref = self.store.capture(self.value, force=True)['ref']

    def tearDown(self):
        self.store.close()
        self.env.stop()
        self.temp.cleanup()

    def test_count_and_group_return_counts_without_record_bodies(self):
        count = self.store.result(self.ref, view='count', query='ok')
        self.assertEqual(count['items'], [{'count': 2}])
        group = self.store.result(self.ref, view='group', fields=['status'])
        self.assertEqual(group['items'], [{'key': 'fail', 'count': 1}, {'key': 'ok', 'count': 2}, {'key': None, 'count': 1}])
        self.assertEqual(group['missingFieldItems'], 1)
        self.assertTrue(group['complete'])
        self.assertEqual(self.store.get(self.ref), self.value)
        page = self.store.result(self.ref, view='group', fields=['status'], limit=1)
        self.assertFalse(page['complete'])
        self.assertEqual(page['nextOffset'], 1)

    def test_scalars_text_lines_and_scan_limits_are_honest(self):
        for value, expected in [(42, 1), ('one\r\ntwo\rthree\n', 3), ([], 0)]:
            ref = self.store.capture(value, force=True)['ref']
            self.assertEqual(self.store.result(ref, view='count')['items'][0]['count'], expected)
        with patch.object(query_aggregates, 'MAX_RECORDS', 2):
            result = self.store.result(self.ref, view='count')
        self.assertEqual(result['items'][0]['count'], 2)
        self.assertEqual(result['scanTruncatedBy'], 'records')
        self.assertFalse(result['complete'])
        with patch.object(query_aggregates, 'MAX_GROUPS', 1):
            result = self.store.result(self.ref, view='group', fields=['status'])
        self.assertEqual(result['scanTruncatedBy'], 'groups')
        self.assertFalse(result['scanComplete'])
        scalar = self.store.capture([1, 1, False, None], force=True)['ref']
        self.assertEqual(self.store.result(scalar, view='group')['items'][0], {'key': 1, 'count': 2})
        self.assertEqual(self.store.result(scalar, view='group', fields=[])['items'][0], {'key': 1, 'count': 2})
        missing = self.store.result(scalar, view='group', fields=['status'])
        self.assertEqual(missing['missingFieldItems'], 4)
        text = self.store.capture('line one\nline two', force=True)['ref']
        self.assertEqual(self.store.result(text, view='count', query='two')['items'][0]['count'], 1)

    def test_invalid_aggregation_is_bounded_and_keeps_the_saved_value(self):
        for options in [{'view': 'count', 'fields': ['status']}, {'view': 'group', 'fields': ['a', 'b']},
                        {'view': 'group', 'fields': [1]}, {'view': 'group'}, {'view': 'count', 'query': 'x' * 201}]:
            self.assertEqual(self.store.result(self.ref, **options)['status'], 'error')
        ref = self.store.capture(['x' * 2000], force=True)['ref']
        self.assertEqual(self.store.result(ref, view='group')['status'], 'error')

    def test_batch_has_one_total_budget_and_keeps_independent_errors_and_cursors(self):
        requests = [{'ref': self.ref, 'view': 'count', 'query': 'ok'},
                    {'ref': self.ref, 'view': 'group', 'fields': ['status'], 'limit': 1},
                    {'ref': 'ops://' + 'f' * 48, 'view': 'outline'}]
        original = copy.deepcopy(requests)
        result = result_batch.run(self.store, requests, 4000)
        self.assertEqual(result['kind'], 'result-batch')
        self.assertTrue(result['complete'])
        self.assertEqual(result['items'][0]['result']['items'], [{'count': 2}])
        self.assertEqual(result['items'][1]['result']['nextOffset'], 1)
        self.assertEqual(result['items'][2]['result']['error']['code'], 'REFERENCE_UNAVAILABLE')
        self.assertLessEqual(len(encode(result).encode()), 4000)
        self.assertEqual(requests, original)
        self.assertEqual(snapshot(root=self.temp.name)['retrievalCosts']['items'], 2)

    def test_batch_rejects_malformed_requests_before_any_retrieval(self):
        invalid = [None, [], [{}] * 9, [{}], [{'ref': self.ref, 'action': 'release'}],
                   [{'ref': self.ref, 'view': 'unknown'}], [{'ref': self.ref, 'path': 'x' * 33000}]]
        with patch.object(self.store, 'result') as retrieve:
            for requests in invalid:
                self.assertEqual(result_batch.run(self.store, requests, 6000)['status'], 'error')
            self.assertEqual(result_batch.run(self.store, [{'ref': self.ref}] * 8, 512)['status'], 'error')
            self.assertEqual(result_batch.run(self.store, [{'ref': self.ref}], 17000)['status'], 'error')
            retrieve.assert_not_called()
        with patch.object(self.store, 'result', return_value={'error': 'x' * 8000}):
            self.assertEqual(result_batch.run(self.store, [{'ref': self.ref}], 1000)['error']['code'], 'BATCH_BUDGET_EXCEEDED')

    def test_all_batch_options_are_validated_before_any_page_is_counted(self):
        invalid = [{'max_bytes': None}, {'max_bytes': 511}, {'max_bytes': 16001}, {'offset': -1},
                   {'offset': True}, {'limit': 0}, {'limit': 201}, {'path': None}, {'path': 'x' * 2049},
                   {'query': None}, {'query': 'x' * 201}, {'fields': 'status'}, {'fields': ['x'] * 33},
                   {'fields': [1]}, {'fields': ['x' * 257]}]
        with patch.object(self.store, 'result') as retrieve:
            for options in invalid:
                requests = [{'ref': self.ref}, {'ref': self.ref, **options}]
                self.assertEqual(result_batch.run(self.store, requests, 4000)['status'], 'error')
            retrieve.assert_not_called()
        result = result_batch.run(self.store, [{'ref': self.ref, 'view': 'raw', 'limit': 1000,
            'max_bytes': 2000, 'offset': 0, 'path': '', 'query': '', 'fields': []}], 3000)
        self.assertEqual(result['kind'], 'result-batch')

    def test_native_surface_batch_catalog_and_search_integration(self):
        result = server.ops_result(action='batch', requests=[{'ref': self.ref, 'view': 'count'}])
        self.assertEqual(result['kind'], 'result-batch')
        self.assertEqual(server.ops_result(self.ref, action='batch', requests=[])['status'], 'error')
        self.assertEqual(server.ops_result(self.ref, requests=[])['status'], 'error')
        self.assertNotEqual(server.ops_catalog('search').get('status'), 'error')
        root = Path(self.temp.name)
        (root / 'module.py').write_text('def target():\n    return 7\n', encoding='utf-8')
        found = files.run(str(root), 'search', {'pattern': 'target', 'path': '.', 'before': 0, 'after': 1})
        self.assertEqual(found['matchChecks'][0]['state'], 'unchanged')
        self.assertEqual(found['context']['items'][0]['items'][1]['text'], '    return 7')

    def test_private_worker_budgets_do_not_expand_native_deadlines(self):
        for invalid in (None, '2', float('inf'), 1, 33):
            with self.assertRaises(ValueError):
                files._timeout(invalid)
        captured = []
        def run(*args, **kwargs):
            captured.append(kwargs)
            return type('Result', (), {'returncode': 0, 'stdout': b'{"status":"completed"}'})()
        with patch.object(files.subprocess, 'run', side_effect=run):
            files._invoke_worker(Path(self.temp.name), 'stat', {'path': '.'}, 3)
            files._invoke_worker(Path(self.temp.name), 'stat', {'path': '.'})
        self.assertEqual(captured[0]['timeout'], 3)
        self.assertEqual(json.loads(captured[0]['input'])['budget']['timeoutMs'], 2000)
        self.assertEqual(json.loads(captured[1]['input'])['budget']['timeoutMs'], 30000)

    def test_malformed_file_requests_return_actionable_errors_without_worker_calls(self):
        requests = [None, {'files': []}, {'files': [None]}, {'files': ['a.txt']},
                    {'files': [{'path': None}]}, {'files': None}]
        with patch.object(files, '_invoke_worker') as invoke:
            for args in requests:
                value = files.run(self.temp.name, 'read', args)
                self.assertEqual(value['error']['code'], 'INVALID_ARGUMENT')
            invoke.assert_not_called()


if __name__ == '__main__':
    unittest.main()
