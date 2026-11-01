import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime_bridge'))
from evidence_preview import preview as evidence, records, text_evidence
from output_budget import FrameBudget
from presentation_policy import Presenter
from projection import SERVICE, project
from reducers import encode, preview
from store import Store
from structured import analyze
from test_frame_dedup import field, response, text_blocks
from wire import fields


class V06EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {'CODEX_OPS_STORE': self.temporary.name})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    def saved(self, receipt):
        store = Store()
        try:
            return store.get(receipt['ref'])
        finally:
            store.close()

    def test_typescript_locations_summary_and_full_raw_are_available(self):
        log = '\n'.join(['checking module ' + str(i) for i in range(80)] + [
            "src/ledger.ts(7,14): error TS2322: Type 'string' is not assignable to type 'number'.",
            'Found 1 error.'])
        value = {'output': log, 'exit_code': 2, 'session_id': None}
        original = copy.deepcopy(value)
        receipt = json.loads(Presenter().render(encode(value)))
        self.assertEqual(value, original)
        self.assertEqual(receipt['preview']['kind'], 'diagnostic-evidence')
        self.assertIn('src/ledger.ts(7,14)', encode(receipt['preview']))
        self.assertIn('Found 1 error.', encode(receipt['preview']))
        self.assertEqual(receipt['metadata']['exit_code'], 2)
        self.assertEqual(self.saved(receipt), encode(value))

    def test_many_failures_report_omissions_and_preserve_completion(self):
        lines = [f'FAILED tests/test_ledger.py::test_case_{i} - AssertionError: value differs' for i in range(60)]
        lines += ['==================== 60 failed in 2.31s ====================']
        result = text_evidence('\n'.join(lines), 1200)
        self.assertEqual(result['diagnosticCount'], 60)
        self.assertGreater(result['omittedDiagnostics'], 0)
        self.assertIn('60 failed in 2.31s', encode(result))
        self.assertLessEqual(len(encode(result).encode()), 1200)
        self.assertTrue(result['previewOnly'])

    def test_traceback_source_location_is_in_evidence(self):
        lines = ['running task'] * 80 + ['Traceback (most recent call last):',
            '  File "src/ledger.py", line 8, in total', '    return 3 / 0',
            'ZeroDivisionError: division by zero']
        shown = evidence(analyze({'output': '\n'.join(lines), 'exit_code': 1}))
        self.assertIn('src/ledger.py', encode(shown))
        self.assertIn('ZeroDivisionError', encode(shown))

    def test_git_diff_and_status_keep_changes_and_omission_counts(self):
        diff = '\n'.join(['diff --git a/a.py b/a.py', '--- a/a.py', '+++ b/a.py', '@@ -1,50 +1,50 @@'] +
            [' unchanged'] * 40 + ['-old_value = 1', '+new_value = 2'])
        shown = preview({'output': diff, 'exit_code': 0})
        self.assertEqual(shown['kind'], 'diff')
        self.assertIn('+new_value = 2', encode(shown))
        status = '\n'.join(['## main'] + [f' M src/file_{i}.ts' for i in range(80)])
        shown = evidence(analyze({'output': status, 'exit_code': 0}))
        self.assertEqual(shown['kind'], 'git-status')
        self.assertGreater(shown['omittedLines'], 0)

    def test_source_text_incomplete_shell_and_unknown_logs_do_not_get_diagnostic_promotion(self):
        source = 'from errors import Error\n' + 'ERROR: example prose\n' * 100
        cases = [source, 'progress ' * 100]
        for text in cases:
            self.assertIsNone(evidence(analyze({'output': text, 'exit_code': 0})))
        self.assertIsNone(evidence(analyze({'output': 'error: still running', 'session_id': 4, 'exit_code': None})))
        self.assertIsNone(evidence(analyze({'output': 'error: bool', 'exit_code': True})))
        self.assertIsNone(evidence(analyze('error: unclassified plain text')))
        self.assertIsNone(text_evidence('error: ' + 'x' * 500, 10))

    def test_mcp_list_surfaces_failed_record_beyond_initial_sample(self):
        items = [{'id': i, 'title': f'Issue {i}', 'body': 'unrelated body ' * 100, 'status': 'open'} for i in range(80)]
        items[75]['status'] = 'failed'
        items[75]['error'] = {'code': 'PIPELINE_FAILED', 'message': 'compile failed'}
        original = copy.deepcopy(items)
        shown = preview({'items': items})
        self.assertEqual(shown['kind'], 'record-evidence')
        self.assertEqual(shown['returnedItems'], 80)
        self.assertEqual(shown['failedItems'], 1)
        self.assertEqual(shown['sample'][0]['index'], 75)
        self.assertIn('PIPELINE_FAILED', encode(shown))
        self.assertEqual(items, original)
        self.assertEqual(records(items, 200)['sample'], [])
        self.assertIsNone(records([{'id': 1, 'body': 'only a generic item'}], 1000))
        for value in (None, {}, [], [1], {'items': None}):
            self.assertIsNone(records(value, 1000))

    def test_frame_budget_compacts_multiple_individually_small_outputs(self):
        texts = [f'file {i}\n' + '\n'.join('source line ' + str(n) for n in range(115)) for i in range(16)]
        self.assertTrue(all(len(x.encode()) < 2048 for x in texts))
        self.assertTrue(all(Presenter().render(x) == x for x in texts))
        raw = response(texts)
        result = project(SERVICE + 'Execute', raw)
        emitted = text_blocks(result)
        self.assertLess(sum(len(x.encode()) for x in emitted), sum(len(x.encode()) for x in texts) * .8)
        for original, shown in zip(texts, emitted):
            receipt = json.loads(shown)
            self.assertEqual(receipt['kind'], 'reference')
            if 'frameBudget' in receipt:
                self.assertEqual(receipt['frameBudget']['scope'], 'same-result-frame')
                self.assertTrue(receipt['frameBudget']['soft'])
            self.assertEqual(self.saved(receipt), original)

    def test_large_output_with_tiny_sentinel_keeps_existing_compact_receipt(self):
        raw = 'retrieval payload ' * 1200
        normal = Presenter().render(raw)
        emitted = text_blocks(project(SERVICE + 'Execute', response([raw, 'RAW_INTACT'])))
        self.assertEqual(emitted, [normal, 'RAW_INTACT'])
        self.assertNotIn('frameBudget', json.loads(emitted[0]))
        self.assertEqual(self.saved(json.loads(emitted[0])), raw)
        self.assertLess(len(emitted[0].encode()), 5000)

    def test_budget_never_replaces_shorter_semantic_evidence_with_larger_generic_preview(self):
        log = '\n'.join([f'test_case_{i} (tests.Case.test_case_{i}) ... ok' for i in range(30)] +
                        ['Ran 30 tests in 0.01s', 'OK'])
        raw = encode({'output': log, 'exit_code': 0})
        normal = Presenter().render(raw)
        self.assertEqual(json.loads(normal)['preview']['kind'], 'test-summary')
        # Even an unattainably small soft target must not enlarge the useful receipt.
        limited = Presenter().render_budgeted(raw, 'text', 100)
        self.assertEqual(limited, normal)
        self.assertEqual(self.saved(json.loads(limited)), raw)

    def test_frame_budget_leaves_explicit_retrieval_pages_and_small_text_exact(self):
        page = encode({'ref': 'ops://' + 'a' * 48, 'view': 'raw', 'text': 'verbatim ' * 1800,
                      'nextOffset': None, 'complete': True})
        original = response([page, 'small'])
        self.assertEqual(project(SERVICE + 'Execute', original), original)
        self.assertEqual(FrameBudget(Presenter(), [10]).render('small'), 'small')

    def test_frame_budget_storage_failure_preserves_every_original_block(self):
        texts = ['failure source ' * 120 + str(i) for i in range(20)]
        original = response(texts)
        with patch('presentation_policy._capture', side_effect=OSError('offline')):
            self.assertEqual(project(SERVICE + 'Execute', original), original)

    def test_native_error_measured_once_and_its_bytes_are_unchanged(self):
        texts = ['source ' * 240 + str(i) for i in range(16)]
        blocks = b''.join(field(2, field(1, field(1, text.encode()))) for text in texts)
        error = field(5, field(1, b'EXPECTED_NATIVE_ERROR'))
        original = field(2, field(1, b'cell') + blocks + error)
        measurements = []
        result = project(SERVICE + 'Execute', original, Presenter(observer=lambda *args: measurements.append(args)))
        preserved = next(item for item in fields(fields(result)[0].value) if item.number == 5)
        self.assertEqual(preserved.raw, error)
        self.assertEqual([x[:2] for x in measurements].count(('error', 'error_preserved')), 1)

    def test_notify_budget_does_not_create_cross_notification_repeat_claims(self):
        text = 'notice ' * 230
        original = field(3, b''.join(field(5, text.encode()) for _ in range(12)))
        result = project(SERVICE + 'OpenSession', original)
        values = [json.loads(item.value) for item in fields(fields(result)[0].value)]
        self.assertTrue(all('sameAsTextBlock' not in value for value in values))
        self.assertTrue(all(self.saved(value) == text for value in values))

    def test_budget_adapter_retains_non_budget_aware_presenter_contract(self):
        class Identity:
            def render(self, text, channel):
                return text
        value = 'x' * 14000
        self.assertEqual(FrameBudget(Identity(), [len(value), len(value)]).render(value), value)


if __name__ == '__main__':
    unittest.main()
