import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

import diagnostic_view
import files
from presentation_policy import Presenter
from reducers import encode
import test_v080_delivery
import verification_workflow
import workflow_diagnostics
import workflow_view


class DiagnosticViewTests(unittest.TestCase):
    setUp = test_v080_delivery.DeliveryTests.setUp
    raw = test_v080_delivery.DeliveryTests.raw

    def fixture(self, repeat=2):
        path = Path(__file__).parent / 'fixtures' / f'late-log-{repeat}-model-input.json'
        return json.loads(path.read_text(encoding='utf-8'))

    def value(self):
        return json.loads(self.fixture()['envelope']['content'][0]['text'])['value']

    def test_actual_failed_case_inputs_keep_log_origin_coverage_and_context_failure(self):
        for repeat in (2, 3):
            fixture = self.fixture(repeat)
            envelope = fixture['envelope']
            original = copy.deepcopy(envelope)
            raw = encode(envelope)
            shown = json.loads(Presenter().render(raw))
            self.assertEqual(shown['kind'], 'workflow-view')
            self.assertEqual(shown['diagnosticCoordinates']['origin'], 'log-file')
            self.assertEqual(shown['diagnosticCoordinates']['path'], 'build.log')
            self.assertEqual(shown['evidence'][0]['logLocation'], {'line': 5001})
            self.assertNotIn('line', shown['evidence'][0])
            self.assertEqual(shown['evidence'][0]['text'],
                             'ERROR EXPORT_SCHEMA expected=3 observed=2 source=src/export.py:2')
            self.assertTrue(shown['logSource']['scanComplete'])
            self.assertEqual(shown['logSource']['nextOffset'], 1)
            self.assertIsNone(shown['logLinesScanned'])
            self.assertNotIn('totalLines', shown['logSource'])
            self.assertEqual(shown['sourceContext']['status'], 'partial')
            failure = shown['sourceContext']['failures'][0]
            self.assertEqual(failure['error']['code'], 'NOT_FOUND')
            self.assertIn('Attempted', shown['sourceContext']['pathMeaning'])
            self.assertNotIn('sourceLocation', shown['evidence'][0])
            self.assertEqual(self.raw(shown['ref']), raw)
            self.assertEqual(envelope, original)

    def test_generic_file_numbers_are_not_source_code_numbers_or_scan_totals(self):
        for line in (1, 83, 94602):
            value = self.value()
            value['logSource'].update(path='C:/logs with spaces/build.log', matchedTotal=None,
                                      complete=False, scanComplete=False, pageComplete=False,
                                      truncated=True, nextOffset=19, continuation={'offset': 19})
            value['diagnostics'] = [{'line': line, 'text': '\x1b[31mERROR File "src/a.py", line 9\x1b[0m', 'clipped': False}]
            before = copy.deepcopy(value)
            shown = workflow_view.project(value)
            self.assertEqual(shown['evidence'][0]['logLocation']['line'], line)
            self.assertIn('line 9', shown['evidence'][0]['text'])
            self.assertEqual(shown['logSource'], value['logSource'])
            self.assertEqual(value, before)

    def test_real_native_log_and_source_context_are_delivered_with_distinct_coordinates(self):
        source = self.root / 'export.py'
        source.write_text('SCHEMA = 3\nraise ValueError("EXPORT_SCHEMA")\n', encoding='utf-8')
        log = self.root / 'build.log'
        log.write_text('INFO ready\n' * 5000 + 'ERROR schema source=export.py:2\n', encoding='utf-8')
        result = workflow_diagnostics.run(str(self.root), {'logPath': 'build.log'}, files.run, None)
        before = copy.deepcopy(result)
        raw = json.dumps({'content': [{'type': 'text', 'text': json.dumps({'kind': 'inline', 'value': result}, indent=2)}]})
        shown = json.loads(Presenter().render(raw))
        diagnostics = [row for row in shown['evidence'] if row['kind'] == 'log-diagnostic']
        context = [row for row in shown['evidence'] if row['kind'] == 'source-context']
        self.assertEqual(diagnostics[0]['logLocation']['line'], 5001)
        self.assertEqual(context[1]['sourceLocation'], {'path': str(source), 'line': 2,
                                                       'revision': result['context']['items'][0]['revision']})
        self.assertEqual(context[1]['text'], 'raise ValueError("EXPORT_SCHEMA")')
        self.assertNotIn('logLocation', context[1])
        self.assertEqual(shown['sourceContext']['shownLines'], 2)
        self.assertEqual(shown['sourceContext']['omittedDisplayLines'], 0)
        self.assertEqual(self.raw(shown['ref']), raw)
        self.assertEqual(result, before)

    def test_source_rows_are_bounded_diverse_and_count_later_frame_omissions(self):
        value = self.value()
        value['context'] = {'status': 'completed', 'complete': True, 'failed': 0,
                            'items': [{'path': name, 'status': 'completed', 'revision': name,
                                       'items': [{'line': i + 1, 'text': 'SOURCE_' + name + str(i)} for i in range(30)]}
                                      for name in ('a.py', 'b.py')]}
        original = copy.deepcopy(value)
        shown = workflow_view.project(value)
        context = [row for row in shown['evidence'] if row['kind'] == 'source-context']
        self.assertEqual(len(context), 24)
        self.assertEqual([row['sourceLocation']['path'] for row in context[:4]], ['a.py', 'b.py', 'a.py', 'b.py'])
        self.assertEqual(shown['sourceContext']['omittedDisplayLines'], 36)
        small = workflow_view.project(value, budget=1300)
        self.assertLess(small['sourceContext']['shownLines'], 24)
        self.assertEqual(small['sourceContext']['shownLines'] + small['sourceContext']['omittedDisplayLines'], 60)
        self.assertLessEqual(len(encode(small).encode()), 1300)
        self.assertEqual(value, original)

    def test_failed_unrelated_or_invalid_source_rows_are_not_verified_context(self):
        good = {'path': 'a.py', 'status': 'partial', 'items': [
            {'line': 2, 'text': 'allowed', 'truncatedInLine': True},
            {'line': 3, 'path': 'other.py', 'text': 'wrong file'}, None,
            {'line': 0, 'text': 'invalid'}, {'line': True, 'text': 'invalid'},
            {'line': 3, 'text': None}]}
        denied = {**good, 'status': 'error', 'error': {'code': 'ACCESS_DENIED'},
                  'items': [{'line': 9, 'text': 'never label verified'}]}
        value = {'operation': 'diagnose', 'diagnostics': [], 'context': {
            'status': 'partial', 'items': [None, denied, {**good, 'error': {'code': 'INCOMPLETE'}},
                                           {'status': 'completed', 'path': None}, good]}}
        shown = workflow_view.project(value)
        self.assertEqual(len(shown['evidence']), 1)
        self.assertEqual(shown['evidence'][0], {'kind': 'source-context', 'sourceLocation': {'path': 'a.py', 'line': 2},
                                               'text': 'allowed', 'truncatedInLine': True})
        self.assertEqual(shown['sourceContext']['failures'][0]['error']['code'], 'ACCESS_DENIED')

    def test_inline_and_saved_logs_use_supplied_text_origin(self):
        content = '\n'.join(['INFO ready'] * 36 + ['ERROR independent message'])
        envelopes = [content, {'output': content, 'exit_code': 2},
                     {'status': 'fulfilled', 'value': {'output': content, 'exit_code': 2}}]
        inputs = [({'log': content}, None)] + [({'logRef': 'ops://example'}, value) for value in envelopes]
        for args, loaded in inputs:
            with self.subTest(args=args, loaded=type(loaded).__name__):
                result = workflow_diagnostics.run(str(self.root), args,
                                                   lambda *args: self.fail('No source command should execute'),
                                                   lambda ref: loaded)
                before = copy.deepcopy(result)
                shown = workflow_view.project(result)
                self.assertEqual(shown['diagnosticCoordinates']['origin'], 'supplied-log-text')
                self.assertNotIn('logSource', shown)
                self.assertEqual(shown['logLinesScanned'], 37)
                self.assertEqual(shown['evidence'][0]['logLocation']['line'], 37)
                self.assertEqual(result, before)

    def test_verify_combined_chunks_do_not_claim_original_file_coordinates(self):
        chunks = [{'output': 'INFO start\n', 'session_id': 5}, {'output': 'ERROR failed\n', 'exit_code': 4}]
        before = copy.deepcopy(chunks)
        def invoke(root, operation, args):
            self.assertEqual(operation, 'diagnose')
            return workflow_diagnostics.run(root, args, None, None)
        result = verification_workflow.run(str(self.root), {'results': chunks}, invoke)
        shown = workflow_view.project(result)
        self.assertEqual(shown['evidence'][0]['logLocation']['line'], 2)
        self.assertEqual(shown['diagnosticCoordinates']['origin'], 'supplied-log-text')
        self.assertEqual(shown['exitCode'], 4)
        self.assertEqual(chunks, before)
        empty = workflow_view.project({'operation': 'verify', 'diagnosis': None, 'exitCode': 0})
        self.assertNotIn('diagnosticCoordinates', empty)

    def test_partial_context_failure_summary_is_bounded_and_preserves_omissions(self):
        value = self.value()
        failure = value['context']['items'][0]
        failure['error']['message'] = 'denied ' * 200
        value['context']['items'] = [copy.deepcopy(failure) for _ in range(9)]
        value['context']['failed'] = 9
        value.update(omittedDiagnostics=8, omittedLocations=3, outsideRootLocations=1)
        shown = workflow_view.project(value)
        self.assertEqual(len(shown['sourceContext']['failures']), 4)
        self.assertEqual(shown['sourceContext']['omittedFailures'], 5)
        self.assertEqual(shown['sourceContext']['failed'], 9)
        self.assertTrue(shown['sourceContext']['failures'][0]['error']['clipped'])
        self.assertEqual(shown['omittedDiagnostics'], 8)
        self.assertEqual(shown['outsideRootLocations'], 1)
        self.assertLessEqual(len(encode(shown).encode()), workflow_view.MAXIMUM)

    def test_no_matches_and_missing_metadata_do_not_invent_file_identity(self):
        value = {'operation': 'diagnose', 'diagnostics': [], 'context': None, 'logSource': None}
        self.assertEqual(workflow_view.project(value)['evidence'], [])
        for context in ({}, {'status': 'completed', 'items': []}):
            value['context'] = context
            shown = workflow_view.project(value)
            self.assertNotIn('logSource', shown)
            self.assertNotIn('logLinesScanned', shown)
            self.assertEqual('sourceContext' in shown, bool(context))

    def test_invalid_locations_are_preserved_without_inventing_coordinates(self):
        rows = [None, {'line': True, 'text': 'ERROR'}, {'line': '12', 'text': 'ERROR'},
                {'line': 0, 'text': 'ERROR'}, {'line': -3}, {'text': 'ERROR'}]
        before = copy.deepcopy(rows)
        view = {}
        projected = diagnostic_view.rows({'diagnostics': rows}, view)
        self.assertEqual(projected, rows)
        self.assertEqual(rows, before)
        self.assertEqual(diagnostic_view._coordinates('')['origin'], 'supplied-log-text')

    def test_small_values_media_and_explicit_raw_retrieval_keep_their_paths(self):
        value = {'operation': 'diagnose', 'status': 'completed', 'diagnostics': [{'line': 1, 'text': 'WARN'}]}
        small = encode({'kind': 'inline', 'value': value})
        self.assertEqual(Presenter().render(small), small)
        mixed = encode({'content': [{'type': 'text', 'text': small}, {'type': 'image', 'data': 'abc', 'mimeType': 'image/png'}]})
        self.assertEqual(Presenter().render(mixed), mixed)
        receipt = self.store.capture('ERROR ' * 2000, force=True)
        page = encode(self.store.result(receipt['ref'], view='raw', max_bytes=6000))
        self.assertEqual(Presenter().render(page), page)

    def test_runtime_import_closure_does_not_require_acquisition_backend(self):
        from runtime_bridge.control import FILES
        stage = self.root / 'runtime'
        for name in FILES:
            if name.endswith('.exe'):
                continue
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(__file__).resolve().parents[1] / name, target)
        script = ('import sys; sys.path.insert(0, sys.argv[1]); import presentation_policy, diagnostic_view; '
                  'assert "workflow_log" not in sys.modules; assert "workflow_validation" not in sys.modules; '
                  'assert diagnostic_view.COVERAGE; print("staged-imports-complete")')
        result = subprocess.run([sys.executable, '-I', '-S', '-c', script, str(stage)],
                                cwd=stage, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('staged-imports-complete', result.stdout)


if __name__ == '__main__':
    unittest.main()
