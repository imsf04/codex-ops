import copy
import json
from pathlib import Path
import tempfile
import unittest

import files
import workflow
import workflow_diagnostics as diagnostics
import workflow_documents as documents
import workflow_incremental as incremental
import workflow_validation as validation
import workflow_preview
from store import Store


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / 'app.py').write_text('one\nneedle two\nthree\nfour\n', encoding='utf-8')
        (self.root / 'notes.txt').write_text('alpha\nneedle evidence\nomega\n', encoding='utf-8')
        (self.root / 'data.csv').write_text('name,value\nneedle,42\nother,17\n', encoding='utf-8')
        self.saved, self.calls = {}, []

    def tearDown(self):
        self.temporary.cleanup()

    def save(self, value):
        ref = 'ops://saved' + str(len(self.saved))
        self.saved[ref] = copy.deepcopy(value)
        return ref

    def invoke(self, root, operation, args):
        self.calls.append((operation, copy.deepcopy(args)))
        return files.run(root, operation, args)

    def run_workflow(self, operation, args, **overrides):
        kwargs = dict(context='trusted-session', invoke=self.invoke, load=self.saved.__getitem__, save=self.save)
        kwargs.update(overrides)
        return workflow.run(str(self.root), operation, args, **kwargs)

    def test_locate_executes_native_search_and_context_as_one_workflow(self):
        result = self.run_workflow('locate', {'pattern': 'needle', 'glob': ['*.py'], 'before': 1, 'after': 1})
        self.assertEqual(result['matches'][0]['text'], 'needle two')
        self.assertEqual(result['matchChecks'][0]['state'], 'unchanged')
        self.assertEqual([c[0] for c in self.calls], ['search'])
        self.assertEqual((self.root / 'app.py').read_text(), 'one\nneedle two\nthree\nfour\n')

    def test_diagnose_reads_native_source_and_retains_failed_log_evidence(self):
        log = 'Traceback:\n  File "app.py", line 2\nAssertionError: expected 3\nFAILED test_example.py::test_a\n'
        result = self.run_workflow('diagnose', {'log': log, 'before': 1, 'after': 1})
        self.assertEqual(result['effectState'], 'none')
        self.assertEqual(result['sourceRequests'][0]['offset'], 1)
        self.assertEqual(result['context']['items'][0]['items'][1]['text'], 'needle two')
        self.assertEqual(result['diagnostics'][0]['text'], 'AssertionError: expected 3')
        self.assertEqual([c[0] for c in self.calls], ['read'])

    def test_diagnose_saved_shell_output_and_rejected_outside_root(self):
        ref = self.save({'output': 'app.py:2: error: bad\napp.py(2,1): warning: also bad\nFile "../outside.py", line 3\n'})
        result = self.run_workflow('diagnose', {'logRef': ref})
        self.assertEqual(result['outsideRootLocations'], 1)
        self.assertEqual(len(result['sourceRequests']), 1)
        self.assertEqual(result['logLinesScanned'], 3)

    def test_diagnose_node_bare_stack_and_rust_arrow_use_exact_source_paths(self):
        node = f'    at {self.root / "app.py"}:2:3'
        rust = '  --> app.py:3:1'
        result = self.run_workflow('diagnose', {'log': node + '\n' + rust, 'before': 0, 'after': 0})
        self.assertEqual([request['path'] for request in result['sourceRequests']], [str(self.root / 'app.py')] * 2)
        self.assertEqual([request['offset'] for request in result['sourceRequests']], [2, 3])
        self.assertEqual(diagnostics._match('    at run (app.py:2:3)'), ('app.py', 2))

    def test_diagnose_saved_auto_output_shell_json_decodes_only_known_envelopes(self):
        log = 'Traceback (most recent call last):\n  File "app.py", line 2\nAssertionError: failed\n'
        shell = {'chunk_id': 'fixture', 'exit_code': 1, 'output': log}
        for value in (log, shell, json.dumps(shell), json.dumps({'content': [{'type': 'text', 'text': json.dumps(shell)}]})):
            result = self.run_workflow('diagnose', {'logRef': self.save(value)})
            self.assertEqual(result['logLinesScanned'], 3)
            self.assertEqual(result['sourceRequests'][0]['path'], str(self.root / 'app.py'))
            self.assertEqual(result['sourceRequests'][0]['offset'], 1)
        arbitrary = json.dumps({'output': 'app.py:2: error: data, not a shell envelope'})
        result = self.run_workflow('diagnose', {'logRef': self.save(arbitrary)})
        self.assertEqual(result['sourceRequests'], [])
        self.assertEqual(result['logLinesScanned'], 1)
        self.assertEqual(result['diagnostics'][0]['text'], arbitrary)
        self.assertEqual(self.run_workflow('diagnose', {'logRef': self.save({'output': 7})})['status'], 'error')

    def test_diagnose_missing_sources_preserves_native_error(self):
        result = self.run_workflow('diagnose', {'log': 'missing.py:2: error: absent'})
        self.assertEqual(result['status'], 'partial')
        self.assertGreater(result['context']['failed'], 0)

    def test_diagnose_no_locations_does_not_invoke_worker(self):
        result = self.run_workflow('diagnose', {'log': 'Ran 3 tests\nOK\n'})
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(self.calls, [])
        empty = self.run_workflow('diagnose', {'log': ''})
        self.assertEqual(empty['diagnostics'], [])

    def test_diagnose_bounds_retains_omission_counts(self):
        log = '\n'.join(f'app.py:{n}: error: {n}' for n in range(1, 5))
        result = self.run_workflow('diagnose', {'log': log, 'maxLocations': 1, 'maxEvidence': 1})
        self.assertEqual(result['omittedLocations'], 3)
        self.assertEqual(result['omittedDiagnostics'], 3)
        self.assertEqual(len(result['sourceRequests']), 1)
        clipped = diagnostics._evidence(['Error: ' + 'x' * 1000], 1)[0][0]
        self.assertTrue(clipped['clipped'])

    def test_diagnostics_strict_validation_happens_before_reads(self):
        bad = [{}, {'log': '', 'logRef': 'ops://x'}, {'log': 'x' * 262145}, {'log': 3},
               {'log': '', 'before': True}, {'log': '', 'maxEvidence': 41}, {'log': '', 'extra': 1}]
        for args in bad:
            self.assertEqual(self.run_workflow('diagnose', args)['status'], 'error', args)
        self.assertEqual(self.calls, [])
        self.assertIsNone(diagnostics._location(str(self.root), ('app.py', 0)))
        self.assertIsNone(diagnostics._location(str(self.root), None))

    def test_documents_filters_real_native_text_and_preserves_exact_reference(self):
        result = self.run_workflow('documents', {'requests': [
            {'operation': 'read', 'args': {'files': [{'path': 'notes.txt'}]}},
            {'operation': 'read_table', 'args': {'path': 'data.csv', 'limit': 2}}],
            'query': 'needle', 'maxEvidence': 2})
        self.assertEqual(result['requestCount'], 2)
        self.assertEqual([c[0] for c in self.calls], ['batch'])
        self.assertTrue(all(item['evidence']['items'] for item in result['items']))
        raw = result['items'][0]['result']
        self.assertEqual(raw['items'][0]['items'][1]['text'], 'needle evidence')
        self.assertTrue(result['items'][0]['evidence']['items'][0]['pointer'].startswith('/items/'))

    def test_documents_preserves_failed_read_and_snapshot_without_rerun(self):
        result = self.run_workflow('documents', {'requests': [{'operation': 'read_pdf', 'args': {'path': 'missing.pdf'}}]})
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['items'][0]['status'], 'error')
        self.assertFalse(result['items'][0]['sourceComplete'])
        self.assertEqual(len(self.saved), 0)
        self.assertIn('error', result['items'][0]['result'])

    def test_document_row_limit_cannot_prove_missing_query_and_exposes_cursor(self):
        result = self.run_workflow('documents', {'requests': [
            {'operation': 'read_table', 'args': {'path': 'data.csv', 'limit': 1}}], 'query': 'other'})
        item = result['items'][0]
        self.assertEqual(result['status'], 'partial')
        self.assertFalse(item['sourceComplete'])
        self.assertEqual(item['evidence']['matchedStrings'], 0)
        self.assertTrue(item['evidence']['scanComplete'])
        self.assertEqual(item['matchConclusion'], 'unknown')
        self.assertEqual(item['result']['nextOffset'], 2)
        self.assertTrue(item['result']['truncated'])
        complete = self.run_workflow('documents', {'requests': [
            {'operation': 'read_table', 'args': {'path': 'data.csv'}}], 'query': 'absent-value'})
        self.assertEqual(complete['items'][0]['matchConclusion'], 'absent-in-complete-response')

    def test_document_nested_source_ranges_and_unscanned_evidence_are_incomplete(self):
        result = self.run_workflow('documents', {'requests': [
            {'operation': 'read', 'args': {'files': [{'path': 'notes.txt', 'limit': 1}]}}], 'query': 'needle'})
        item = result['items'][0]
        self.assertFalse(item['sourceComplete'])
        self.assertEqual(item['result']['items'][0]['nextOffset'], 2)
        self.assertEqual(item['matchConclusion'], 'unknown')
        self.assertFalse(validation.complete({'status': 'completed', 'scanComplete': False}))
        self.assertFalse(validation.complete({'status': 'completed', 'pending': 1}))
        self.assertFalse(validation.complete({'status': 'completed', 'items': [{'status': 'error'}]}))
        self.assertEqual(documents._conclusion({'matchedStrings': 0, 'scanComplete': False}, True), 'unknown')

    def test_document_scan_and_preview_bounds_are_explicit(self):
        result = documents.evidence({'a/b~c': ['hit' * 300, 'hit', 'hit']}, 'hit', 1)
        self.assertEqual(result['items'][0]['pointer'], '/a~1b~0c/0')
        self.assertTrue(result['items'][0]['clipped'])
        self.assertEqual(result['omittedMatches'], 2)
        bounded = documents.evidence(['hit'] * 5000, 'hit', 1)
        self.assertFalse(bounded['scanComplete'])
        self.assertEqual(bounded['nodesScanned'], documents.MAX_NODES)
        late = documents.evidence('x' * 500 + 'needle', 'needle', 1)['items'][0]
        self.assertEqual(late['characterOffset'], 420)

    def test_document_invalid_batches_never_read_or_save(self):
        for requests in ([], [None], [{'operation': 'write', 'args': {}}], [{'operation': 'read', 'args': None}], [{}] * 5):
            self.assertEqual(self.run_workflow('documents', {'requests': requests})['status'], 'error')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.saved, {})
        failed = self.run_workflow('documents', {'requests': [{'operation': 'read', 'args': {}}]},
            invoke=lambda *_: {'status': 'error', 'code': 'fixture'})
        self.assertEqual(failed['code'], 'fixture')

    def test_incremental_returns_first_full_window_then_exact_changed_lines(self):
        args = {'files': [{'path': 'app.py', 'offset': 1, 'limit': 4}]}
        first = self.run_workflow('incremental', args)
        self.assertEqual(first['items'][0]['mode'], 'full')
        self.assertFalse(first['contextRetentionAssumed'])
        (self.root / 'app.py').write_text('one\nneedle changed\nthree\nfour\n')
        second = self.run_workflow('incremental', {**args, 'baselineRef': first['snapshotRef']})
        item = second['items'][0]
        self.assertEqual(item['mode'], 'delta')
        self.assertFalse(item['sameFileRevision'])
        self.assertEqual(item['changes'][0]['lines'][0]['text'], 'needle changed')
        self.assertEqual(item['changes'][0]['oldLines'], [2])
        self.assertEqual(item['omittedUnchangedLines'], 3)
        full = self.saved[second['snapshotRef']]['result']['items'][0]['items']
        self.assertEqual(len(full), 4)
        self.assertEqual(full[1]['text'], 'needle changed')

    def test_incremental_unchanged_and_change_outside_window_are_distinguished(self):
        args = {'files': [{'path': 'app.py', 'limit': 1}]}
        first = self.run_workflow('incremental', args)
        same = self.run_workflow('incremental', {**args, 'baselineRef': first['snapshotRef']})
        self.assertTrue(same['items'][0]['sameFileRevision'])
        self.assertEqual(same['items'][0]['changes'], [])
        (self.root / 'app.py').write_text('one\nnew outside requested window\n')
        changed = self.run_workflow('incremental', {**args, 'baselineRef': first['snapshotRef']})
        self.assertFalse(changed['items'][0]['sameFileRevision'])
        self.assertEqual(changed['items'][0]['changes'], [])

    def test_incremental_session_root_and_range_mismatch_reject_before_read(self):
        args = {'files': [{'path': 'app.py'}]}
        first = self.run_workflow('incremental', args)
        self.calls.clear()
        wrong_session = self.run_workflow('incremental', {**args, 'baselineRef': first['snapshotRef']}, context='another')
        changed_range = self.run_workflow('incremental', {'files': [{'path': 'app.py', 'limit': 3}], 'baselineRef': first['snapshotRef']})
        wrong_kind = self.run_workflow('incremental', {**args, 'baselineRef': self.save({})})
        for result in (wrong_session, changed_range, wrong_kind):
            self.assertEqual(result['status'], 'error')
        self.assertEqual(self.calls, [])

    def test_incremental_missing_and_deleted_files_remain_failed_full_results(self):
        args = {'files': [{'path': 'missing.py'}]}
        first = self.run_workflow('incremental', args)
        second = self.run_workflow('incremental', {**args, 'baselineRef': first['snapshotRef']})
        self.assertEqual(second['items'][0]['mode'], 'full')
        self.assertGreater(second['failed'], 0)

    def test_incremental_duplicate_ranges_and_invalid_bounds_rejected(self):
        for rows in ([], [{'path': 'app.py'}] * 2, [{'path': 'app.py', 'limit': 301}], [{'path': 4}], [None]):
            self.assertEqual(self.run_workflow('incremental', {'files': rows})['status'], 'error')
        missing_callback = self.run_workflow('incremental', {'files': [{'path': 'app.py'}]}, save=None)
        self.assertEqual(missing_callback['status'], 'error')
        self.assertEqual(self.calls, [])

    def test_sdk_is_explicit_callable_source_not_native_registration(self):
        value = self.run_workflow('sdk', {})
        self.assertIn('function createOps', value['javascript'])
        self.assertIn('interface OpsWorkflow', value['typescript'])
        self.assertIn('No native registry is modified', value['installation'])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.run_workflow('sdk', {'bogus': True})['status'], 'error')

    def test_dispatch_root_context_and_adapter_errors_are_values(self):
        self.assertEqual(self.run_workflow('write', {})['status'], 'error')
        self.assertEqual(workflow.run('relative', 'sdk', {}, 'x')['status'], 'error')
        self.assertEqual(workflow.run(1, 'sdk', {}, 'x')['status'], 'error')
        self.assertEqual(self.run_workflow('sdk', {}, context='')['status'], 'error')
        self.assertEqual(self.run_workflow('diagnose', {'logRef': 'ops://absent'})['status'], 'error')
        self.assertFalse(validation.complete({'status': 'rejected'}))

    def test_workflow_receipts_retain_actionable_evidence_and_exact_result(self):
        log = '\n'.join(f'app.py:2: error: evidence {n} ' + 'detail ' * 70 for n in range(30))
        value = self.run_workflow('diagnose', {'log': log, 'maxEvidence': 30})
        store = Store(self.root / 'cache')
        try:
            receipt = workflow_preview.capture(store, value, 'diagnose')
            self.assertEqual(store.get(receipt['ref']), value)
            self.assertTrue(receipt['preview']['evidence'][0]['value']['text'].startswith('app.py:2: error: evidence 0'))
            self.assertGreater(receipt['preview']['omittedPreviewRows'], 0)
            self.assertLessEqual(len(json.dumps(receipt['preview'], ensure_ascii=False).encode()), 3500)
            small = workflow_preview.capture(store, {'status': 'completed'}, 'sdk')
            self.assertEqual(small['kind'], 'inline')
            located = self.run_workflow('locate', {'pattern': 'needle'})
            self.assertIn(workflow_preview.capture(store, located, 'locate')['kind'], ('reference', 'inline'))
        finally:
            store.close()

    def test_document_and_incremental_previews_have_refs_and_change_lines(self):
        doc = self.run_workflow('documents', {'requests': [{'operation': 'read', 'args': {'files': [{'path': 'notes.txt'}]}}], 'query': 'needle'})
        preview = workflow_preview.preview(doc, 'documents')
        self.assertIn('result', preview['evidence'][0]['value'])
        self.assertEqual(preview['evidence'][0]['pointer'], '/items/0/result')
        args = {'files': [{'path': 'app.py'}]}
        first = self.run_workflow('incremental', args)
        (self.root / 'app.py').write_text('changed\n')
        changed = self.run_workflow('incremental', {**args, 'baselineRef': first['snapshotRef']})
        preview = workflow_preview.preview(changed, 'incremental')
        self.assertEqual(preview['evidence'][1]['value']['lines'][0]['text'], 'changed')
        self.assertEqual(preview['snapshotRef'], changed['snapshotRef'])
        self.assertEqual(workflow_preview.preview({}, 'sdk')['evidence'], [])


if __name__ == '__main__':
    unittest.main()
