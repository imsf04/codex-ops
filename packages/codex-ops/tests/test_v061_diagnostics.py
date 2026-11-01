import copy
import json
from pathlib import Path
import tempfile
import unittest

import files
import workflow
import workflow_log


class LogPathTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.calls = []

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, root, operation, args):
        self.calls.append((operation, copy.deepcopy(args)))
        return files.run(root, operation, args)

    def run_diagnose(self, args, **kwargs):
        return workflow.run(str(self.root), 'diagnose', args, 'log-test-owner',
                            invoke=kwargs.get('invoke', self.invoke), load=kwargs.get('load'))

    def test_path_finds_late_error_without_sending_success_prefix_to_model(self):
        log = self.root / 'build.log'
        log.write_text('INFO status=passed\n' * 5000 + 'ERROR primary=INVALID_REGION\n', encoding='utf-8')
        original = log.read_bytes()
        result = self.run_diagnose({'logPath': 'build.log'})
        self.assertEqual(result['diagnostics'], [{'line': 5001, 'text': 'ERROR primary=INVALID_REGION', 'clipped': False}])
        self.assertEqual([entry[0] for entry in self.calls], ['stat', 'grep'])
        self.assertTrue(result['logSource']['scanComplete'])
        self.assertTrue(result['logSource']['pageComplete'])
        self.assertIsNone(result['logLinesScanned'])
        self.assertEqual(log.read_bytes(), original)

    def test_path_traceback_reads_source_context_and_keeps_log_line_number(self):
        (self.root / 'source.py').write_text('a = 1\nraise ValueError("broken")\n', encoding='utf-8')
        (self.root / 'build.log').write_text('INFO starting\nTraceback:\n  File "source.py", line 2\n    raise ValueError("broken")\nValueError: broken\n', encoding='utf-8')
        result = self.run_diagnose({'logPath': str(self.root / 'build.log'), 'before': 1, 'after': 0})
        self.assertEqual([row['line'] for row in result['diagnostics']], [4, 5])
        self.assertEqual(result['sourceRequests'][0]['offset'], 1)
        self.assertEqual(result['context']['items'][0]['items'][1]['text'], 'raise ValueError("broken")')
        self.assertEqual([entry[0] for entry in self.calls], ['stat', 'grep', 'read'])

    def test_no_failure_selects_warning_or_summary_without_claiming_success(self):
        (self.root / 'build.log').write_text('INFO started\nWARN cache fallback\n3 tests passed\n', encoding='utf-8')
        result = self.run_diagnose({'logPath': 'build.log'})
        self.assertEqual([row['line'] for row in result['diagnostics']], [2, 3])
        self.assertEqual(result['logSource']['selection'], 'warning-or-summary')
        self.assertEqual([entry[0] for entry in self.calls], ['stat', 'grep', 'grep'])
        (self.root / 'empty.log').write_text('', encoding='utf-8')
        empty = self.run_diagnose({'logPath': 'empty.log'})
        self.assertEqual(empty['diagnostics'], [])
        self.assertIn('no total-log-line count', empty['logSource']['coverageMeaning'])

    def test_native_restrictions_and_read_errors_are_preserved(self):
        (self.root / 'directory').mkdir()
        for path in ('../outside.log', '.env', 'missing.log', 'directory'):
            result = self.run_diagnose({'logPath': path})
            self.assertEqual(result['status'], 'error', path)
            self.assertIn('error', result)
        self.assertEqual(len(self.calls), 5)

    def test_three_log_inputs_are_exclusive_and_validate_before_worker(self):
        invalid = [{'logPath': ''}, {'logPath': 9}, {'logPath': 'x', 'log': ''},
                   {'logPath': 'x', 'logRef': 'ops://x'},
                   {'logPath': 'x', 'maxEvidence': 0}, {'logPath': 'x', 'before': True}]
        for args in invalid:
            self.assertEqual(self.run_diagnose(args)['status'], 'error', args)
        self.assertEqual(self.calls, [])

    def test_partial_native_scan_and_page_bounds_remain_explicit(self):
        native = {'status': 'completed', 'items': [{'line': 8, 'text': 'a\nb\nc\nERROR failure', 'path': str(self.root / 'build.log')}],
                  'scanComplete': False, 'pageComplete': False, 'complete': False,
                  'omitted': 5, 'nextOffset': 1, 'truncated': True, 'truncatedBy': 'maxBytes',
                  'skippedFiles': 1, 'skipReasons': {'size': 1}}
        result = self.run_diagnose({'logPath': 'build.log'}, invoke=lambda *unused: native)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['diagnostics'][0]['line'], 8)
        self.assertEqual(result['diagnostics'][0]['text'], 'ERROR failure')
        self.assertEqual(result['omittedDiagnostics'], 5)
        self.assertFalse(result['logSource']['scanComplete'])
        self.assertEqual(result['logSource']['nextOffset'], 1)
        self.assertEqual(result['logSource']['skipReasons'], {'size': 1})
        empty = {**native, 'items': []}
        calls = []
        def invoke(*unused):
            calls.append(True)
            return empty
        self.assertEqual(self.run_diagnose({'logPath': 'build.log'}, invoke=invoke)['status'], 'partial')
        self.assertEqual(len(calls), 2)

    def test_invalid_native_rows_fail_explicitly_and_long_matches_are_marked(self):
        for row in (None, {}, {'line': True, 'text': 'ERROR'}, {'line': 0, 'text': 'ERROR'},
                    {'line': 1, 'text': 7}, {'line': 5, 'text': 'ERROR'}):
            native = {'status': 'completed', 'items': [row]}
            self.assertEqual(self.run_diagnose({'logPath': 'x'}, invoke=lambda *a: native)['status'], 'error')
        evidence = workflow_log._evidence({'line': 1, 'text': 'ERROR ' + 'x' * 900})
        self.assertTrue(evidence['clipped'])
        self.assertEqual(len(evidence['text']), 800)

    def test_changed_path_does_not_attribute_another_file_as_the_requested_log(self):
        native = {'status': 'completed', 'items': [{'line': 1, 'text': 'ERROR elsewhere',
                                                  'path': str(self.root / 'other.log')}]}
        result = self.run_diagnose({'logPath': 'build.log'}, invoke=lambda *unused: native)
        self.assertEqual(result['status'], 'error')
        self.assertIn('different source', result['error']['message'])

    def test_fulfilled_shell_reference_decodes_exact_supported_envelope(self):
        log = 'INFO one\nERROR two\n'
        wrapper = {'status': 'fulfilled', 'value': {'chunk_id': 'test', 'exit_code': 1, 'output': log}}
        for value in (wrapper, json.dumps(wrapper)):
            result = self.run_diagnose({'logRef': 'ops://test'}, load=lambda ref: value)
            self.assertEqual(result['logLinesScanned'], 2)
            self.assertEqual(result['diagnostics'][0]['line'], 2)
            self.assertEqual(result['diagnostics'][0]['text'], 'ERROR two')
        for value in ({**wrapper, 'status': 'rejected'}, {**wrapper, 'extra': True},
                      {'status': 'fulfilled', 'value': {'output': log}}):
            result = self.run_diagnose({'logRef': 'ops://test'}, load=lambda ref: json.dumps(value))
            self.assertEqual(result['logLinesScanned'], 1)
            self.assertEqual(result['sourceRequests'], [])


if __name__ == '__main__':
    unittest.main()
