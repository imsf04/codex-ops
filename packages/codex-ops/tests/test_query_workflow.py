import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import files
import query_workflow as workflow


class QueryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'a.txt').write_text('one\nneedle first\nneedle second\nfour\nfive\n', encoding='utf-8')
        (self.root / 'b.txt').write_text('first\nneedle third\nlast\n', encoding='utf-8')
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, operation, args, seconds):
        self.calls.append((operation, copy.deepcopy(args), seconds))
        return files.run(str(self.root), operation, args)

    def run_query(self, args, invoke=None, clock=None):
        options = {'clock': clock} if clock is not None else {}
        return workflow.run(str(self.root), args, invoke or self.invoke, **options)

    def test_native_search_merges_context_and_preserves_values_and_revisions(self):
        args = {'pattern': 'needle', 'before': 1, 'after': 1}
        original = copy.deepcopy(args)
        result = self.run_query(args)
        self.assertEqual(args, original)
        self.assertEqual([call[0] for call in self.calls], ['grep', 'read'])
        self.assertEqual(len(result['requestedRanges']), 2)
        first = result['requestedRanges'][0]
        self.assertEqual((first['offset'], first['limit']), (1, 4))
        self.assertEqual(result['selectedMatches'], 3)
        self.assertEqual(result['omittedMatches'], 0)
        self.assertTrue(all(row['state'] == 'unchanged' for row in result['matchChecks']))
        self.assertTrue(all(row['revision'] for row in result['context']['items']))
        self.assertIn('non-atomic', result['snapshotConsistency'])
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(all(0 < call[2] <= 22 for call in self.calls))

    def test_bounds_keep_source_paging_and_unread_files_explicit(self):
        result = self.run_query({'pattern': 'needle', 'maxMatches': 2, 'maxFiles': 1, 'before': 0, 'after': 0})
        self.assertEqual(len(result['matches']), 2)
        self.assertEqual(result['search']['nextOffset'], 2)
        self.assertFalse(result['search']['scanComplete'])
        self.assertEqual(result['status'], 'partial')
        omitted = self.run_query({'pattern': 'needle', 'maxFiles': 1})
        self.assertEqual(omitted['omittedMatches'], 1)
        self.assertEqual(omitted['selectedMatches'], 2)
        self.assertEqual(omitted['status'], 'partial')

    def test_offset_case_and_glob_reach_native_search(self):
        result = self.run_query({'pattern': 'NEEDLE', 'caseInsensitive': True, 'glob': ['a.txt'], 'offset': 1})
        self.assertEqual(len(result['matches']), 1)
        self.assertEqual(result['matches'][0]['line'], 3)

    def test_no_matches_does_not_start_read_phase(self):
        result = self.run_query({'pattern': 'not present'})
        self.assertEqual([call[0] for call in self.calls], ['grep'])
        self.assertEqual(result['context']['items'], [])
        self.assertEqual(result['status'], 'completed')

    def test_changed_match_is_reported_without_claiming_atomic_snapshot(self):
        def invoke(operation, args, seconds):
            value = self.invoke(operation, args, seconds)
            if operation == 'grep':
                (self.root / 'a.txt').write_text('one\nchanged line\nneedle second\nfour\nfive\n')
            return value
        result = self.run_query({'pattern': 'needle'}, invoke)
        self.assertEqual(result['matchChecks'][0]['state'], 'changed')
        self.assertEqual(result['matches'][0]['text'], 'needle first')
        self.assertEqual(result['context']['items'][0]['items'][1]['text'], 'changed line')
        self.assertEqual(result['status'], 'partial')

    def test_deleted_file_keeps_error_and_match_unavailability(self):
        def invoke(operation, args, seconds):
            value = self.invoke(operation, args, seconds)
            if operation == 'grep':
                (self.root / 'a.txt').unlink()
            return value
        result = self.run_query({'pattern': 'needle'}, invoke)
        self.assertEqual(result['matchChecks'][0]['state'], 'unavailable')
        self.assertEqual(result['context']['items'][0]['status'], 'error')
        self.assertEqual(result['status'], 'partial')

    def test_native_root_and_credential_fences_still_apply(self):
        (self.root / '.env').write_text('needle')
        for path, code in [('../outside', 'PATH_RESTRICTED'), ('.env', 'CREDENTIAL_DENIED')]:
            result = self.run_query({'pattern': 'needle', 'path': path})
            self.assertEqual(result['error']['code'], code)

    def test_invalid_options_are_rejected_before_worker_execution(self):
        invalid = [None, [], {}, {'pattern': ''}, {'pattern': 1}, {'pattern': 'a', 'path': ''},
                   {'pattern': 'a', 'other': 1}, {'pattern': 'a', 'maxMatches': True},
                   {'pattern': 'a', 'maxFiles': 9}, {'pattern': 'a', 'before': -1},
                   {'pattern': 'a', 'glob': '*.txt'}, {'pattern': 'a', 'glob': ['']},
                   {'pattern': 'a', 'glob': ['a'] * 33}, {'pattern': 'a', 'caseInsensitive': 'yes'}]
        for args in invalid:
            self.assertEqual(self.run_query(args)['status'], 'error')
        self.assertEqual(self.calls, [])

    def test_shared_deadline_reports_unavailable_context_without_retry(self):
        clock = iter([0, 0, 44])
        result = self.run_query({'pattern': 'needle'}, clock=lambda: next(clock))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['context']['error']['code'], 'WORKFLOW_TIMEOUT')
        self.assertTrue(all(row['state'] == 'unavailable' for row in result['matchChecks']))

    def test_range_cap_and_unknown_native_shapes_are_honest(self):
        rows = [{'path': str(self.root / 'a.txt'), 'line': 1 + n * 50, 'text': 'needle'} for n in range(64)]
        def invoke(operation, args, seconds):
            if operation == 'grep':
                return {'status': 'completed', 'scanComplete': True, 'items': rows}
            return {'status': 'partial', 'items': [], 'pending': len(args['files'])}
        result = self.run_query({'pattern': 'needle', 'maxMatches': 64}, invoke)
        self.assertEqual(len(result['requestedRanges']), 32)
        self.assertEqual(result['omittedRanges'], 32)
        self.assertEqual(result['omittedMatches'], 32)
        for bad in [None, [None], [{'path': 'a', 'line': 0, 'text': 'a'}]]:
            returned = self.run_query({'pattern': 'needle'}, lambda *_: {'items': bad})
            self.assertEqual(returned['error']['code'], 'SEARCH_SHAPE')
        self.assertEqual(self.run_query({'pattern': 'needle'}, lambda *_: {'status': 'rejected', 'error': 1})['status'], 'rejected')
        self.assertEqual(self.run_query({'pattern': 'needle'}, lambda *_: (_ for _ in ()).throw(ValueError('invalid')))['status'], 'error')

    def test_truncated_context_never_claims_complete_workflow(self):
        for key in ('truncated', 'pending', 'failed'):
            def invoke(operation, args, seconds):
                result = self.invoke(operation, args, seconds)
                if operation == 'read':
                    result[key] = 1
                return result
            self.assertEqual(self.run_query({'pattern': 'needle'}, invoke)['status'], 'partial')


if __name__ == '__main__':
    unittest.main()
