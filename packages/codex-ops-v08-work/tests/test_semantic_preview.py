import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from presentation_policy import Presenter, _beneficial
from reducers import encode, preview, payload
import semantic_preview
from store import Store
from structured import analyze


def unittest_log(count=12, ending='OK'):
    return '\n'.join([f'test_case_{i:02} (tests.ExampleTests.test_case_{i:02}) ... ok' for i in range(count)] +
                     ['', '-' * 70, f'Ran {count} tests in 0.123s', '', ending])


class SemanticPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'CODEX_OPS_STORE': self.temp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_completed_medium_test_log_keeps_evidence_and_raw_object_exact(self):
        value = {'output': unittest_log(20), 'exit_code': 0, 'wall_time_seconds': 0.3, 'chunk_id': 'abc'}
        before = copy.deepcopy(value)
        raw = encode(value)
        self.assertTrue(768 <= len(raw.encode()) < 2048)
        shown = json.loads(Presenter().render(raw))
        self.assertEqual(value, before)
        self.assertEqual(shown['preview']['kind'], 'test-summary')
        evidence = [line['text'] for line in shown['preview']['evidence']]
        self.assertIn('Ran 20 tests in 0.123s', evidence)
        self.assertIn('OK', evidence)
        self.assertEqual(shown['metadata']['exit_code'], 0)
        self.assertGreater(shown['preview']['omittedRoutineLines'], 20)
        self.assertLessEqual(len(encode(shown).encode()), len(raw.encode()) * 0.8)
        store = Store()
        self.assertEqual(store.get(shown['ref']), raw)
        store.close()

    def test_failure_summary_keeps_all_nonroutine_diagnostic_context(self):
        log = unittest_log(28, 'FAILED (failures=1)')
        log += '\nFAIL: test_bad (suite.Test)\nTraceback (most recent call last):\n  File "x.py", line 12\nAssertionError: expected 7\n  original comparison context'
        raw = encode({'output': log, 'exit_code': 7})
        shown = json.loads(Presenter().render(raw))
        self.assertEqual(shown['metadata']['exit_code'], 7)
        evidence = '\n'.join(row['text'] for row in shown['preview']['evidence'])
        for line in ['FAILED (failures=1)', 'AssertionError: expected 7', '  original comparison context']:
            self.assertIn(line, evidence)

    def test_build_summary_never_drops_warning_counts_or_unrecognized_lines(self):
        log = '\n'.join([f'   Compiling dependency_{i} v1.2.3' for i in range(30)] +
                        ['warning: API is deprecated', 'Build succeeded.', '    2 Warning(s)',
                         '    0 Error(s)', 'Time Elapsed 00:00:01.23', 'published report at /tmp/result'])
        shown = json.loads(Presenter().render(encode({'output': log, 'exit_code': 0})))
        evidence = '\n'.join(row['text'] for row in shown['preview']['evidence'])
        self.assertEqual(shown['preview']['kind'], 'build-summary')
        for line in ['warning: API is deprecated', '2 Warning(s)', '0 Error(s)', 'published report at /tmp/result']:
            self.assertIn(line, evidence)

    def test_running_tiny_unknown_and_nonbeneficial_outputs_stay_intact(self):
        values = [{'output': unittest_log(20), 'session_id': 3, 'exit_code': None},
                  {'output': unittest_log(1), 'exit_code': 0},
                  {'output': 'critical unstructured value\n' * 30, 'exit_code': 0},
                  {'ordinary': ['x'] * 400}]
        for value in values:
            raw = encode(value)
            self.assertEqual(Presenter().render(raw), raw)
        self.assertFalse(_beneficial('x' * 800, 'y' * 700, {}))
        self.assertTrue(_beneficial('x' * 800, 'y' * 700, None))
        self.assertIsNone(semantic_preview.preview(analyze({'output': 'Ran 1 test in 0.1s\nnot finished', 'exit_code': 0})))
        self.assertIsNone(semantic_preview.preview(analyze({'output': unittest_log(20) + '\n' + 'unknown ' * 500, 'exit_code': 0})))

    def test_source_and_markdown_error_words_do_not_become_diagnostic_logs(self):
        for text in ['# Error handling\nErrors are returned, failures retain state.\nERROR: example only',
                     '"""Exceptions and failure handling."""\ndef failed():\n    raise ValueError("error")',
                     'The error field describes a failure.\nThere are no diagnostic lines.']:
            shown = preview(text)
            self.assertEqual(shown['kind'], 'text')
            self.assertNotIn('diagnostics', shown)
        source = '# Example test output\n' + unittest_log(20)
        raw = encode({'output': source, 'exit_code': 0})
        self.assertEqual(Presenter().render(raw), raw)
        for prefix in ['#!/usr/bin/python', '```text', 'const sample = `', 'package sample']:
            source = prefix + '\n' + unittest_log(20)
            self.assertIsNone(semantic_preview.preview(analyze({'output': source, 'exit_code': 0})))

    def test_diagnostics_are_anchored_and_actual_failure_survives_warning_prefix(self):
        log = '\n'.join(['warning: caution'] * 20 + ['ERROR: precise failure', 'last'])
        shown = preview(log)
        self.assertEqual(shown['kind'], 'diagnostic-log')
        self.assertEqual(shown['diagnostics'], ['ERROR: precise failure'])
        for line in ['E   AssertionError: bad', '[worker] ERROR: failed', '2026-10-29T12:00:00Z ERROR: bad', 'error 0']:
            self.assertTrue(semantic_preview.diagnostic(line))
        for line in ['def failure():', 'return error(code, message)', 'Errors are retained', 'error = None']:
            self.assertFalse(semantic_preview.diagnostic(line))

    def test_exact_inline_envelopes_unwrap_for_presentation_only(self):
        value = {'output': unittest_log(20), 'exit_code': 0}
        for wrapped in [{'kind': 'inline', 'value': value},
                        {'structuredContent': {'kind': 'inline', 'value': value}},
                        {'content': [{'type': 'text', 'text': encode({'kind': 'inline', 'value': value})}]}]:
            before = copy.deepcopy(wrapped)
            self.assertEqual(payload(encode(wrapped)), value)
            self.assertEqual(wrapped, before)
        for value in [None, 3, {'kind': 'inline', 'value': 1, 'extra': True}, {'kind': 'other', 'value': 1}]:
            self.assertEqual(semantic_preview.preview(analyze(value)), None)

    def test_jest_pytest_cargo_formats_keep_summary_and_skipped_reasons(self):
        logs = [('\n'.join(['PASS src/example.test.js'] * 20 + ['Test Suites: 1 passed, 1 total', 'Tests: 20 passed, 20 total']), 'test-summary'),
                ('\n'.join(['tests/test_a.py .... [ 50%]'] * 20 + ['===== 80 passed in 0.05s =====']), 'test-summary'),
                ('\n'.join(['test module::example ... ok'] * 20 + ['test result: ok. 20 passed; 0 failed; 0 ignored']), 'test-summary'),
                ('\n'.join(['Checking crate v0.1.0'] * 20 + ['Finished `dev` profile [unoptimized] target(s) in 1.0s']), 'build-summary')]
        for text, kind in logs:
            result = semantic_preview.preview(analyze({'output': text, 'exit_code': 0}))
            self.assertEqual(result['kind'], kind)
        colored = '\x1b[32m' + unittest_log(20).replace('\n', '\x1b[0m\n\x1b[32m') + '\x1b[0m'
        color_result = semantic_preview.preview(analyze({'output': colored, 'exit_code': 0}))
        self.assertEqual(color_result['evidence'][-1]['text'], 'OK')
        text = unittest_log(10) + '\ntest_skip (suite.Test.test_skip) ... skipped missing service'
        result = semantic_preview.preview(analyze({'output': text, 'exit_code': 0}))
        self.assertIn('missing service', result['evidence'][-1]['text'])

    def test_diff_preview_selects_actual_changes_in_the_middle(self):
        lines = ['diff --git a/a.py b/a.py', '--- a/a.py', '+++ b/a.py', '@@ -1,50 +1,50 @@']
        lines += [' unchanged'] * 20 + ['-old_value = 1', '+new_value = 2'] + [' unchanged'] * 20
        shown = preview('\n'.join(lines))
        self.assertEqual(shown['kind'], 'diff')
        self.assertIn('-old_value = 1', shown['text'])
        self.assertIn('+new_value = 2', shown['text'])

    def test_new_aggregate_and_batch_retrievals_bypass_recapture(self):
        reference = 'ops://' + 'a' * 48
        pages = [{'ref': reference, 'view': view, 'items': ['saved ' * 700], 'nextOffset': None, 'complete': True}
                 for view in ('count', 'group')]
        batch = {'kind': 'result-batch', 'requestCount': 3, 'complete': True, 'sourceCompleteness': 'per-result',
                 'items': [{'index': index, 'result': page} for index, page in enumerate(pages)] +
                          [{'index': 2, 'result': {'status': 'error', 'error': {'code': 'REFERENCE_UNAVAILABLE'}}}]}
        with patch('presentation_policy._capture', side_effect=AssertionError('recaptured')):
            for value in [*pages, batch]:
                self.assertEqual(Presenter().render(encode(value)), encode(value))
        from presentation_policy import _result_batch
        invalid = [{}, {'kind': 'result-batch', 'complete': False},
                   {**batch, 'requestCount': True}, {**batch, 'requestCount': 0},
                   {**batch, 'requestCount': 9}, {**batch, 'items': {}},
                   {**batch, 'items': []}]
        for row in [None, {'index': 9}, {'index': 0, 'result': None}, {'index': 0, 'result': {}},
                    {'index': 0, 'result': {**pages[0], 'ref': 'bad'}},
                    {'index': 0, 'result': {'status': 'error', 'error': None}},
                    {'index': 0, 'result': batch}]:
            invalid.append({'kind': 'result-batch', 'requestCount': 1, 'complete': True, 'items': [row]})
        for value in invalid:
            self.assertFalse(_result_batch(value))


if __name__ == '__main__':
    unittest.main()
