"""Real file/store boundaries for automatic evidence and native display diagnostics."""
import copy
from contextlib import closing
import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import files
import investigate_query
import native_observation_view
import session_scope
import structured
import workflow_entry
import workflow_memory
import working_set
import working_set_sources
import working_set_current
from presentation_policy import Presenter
from store import Store

OWNER = {'session': '01a18391-1809-7601-96cc-09b2c96329c1', 'policy': 'workspace', 'runtime': 'test'}


class EvidenceMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / 'limits.py'
        self.file.write_text('LIMIT = 17\ndef cap(n):\n    return min(n, LIMIT)\n')
        self.store = Store(self.root / 'store')
        self.addCleanup(self.store.close)
        self.scope = session_scope.bind(OWNER)
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)
        self.args = {'question': 'Where is LIMIT?', 'paths': ['limits.py']}

    def packet(self, path=None):
        path = self.file if path is None else path
        read = files.run(str(self.root), 'read', {'files': [{'path': str(path), 'offset': 1, 'limit': 10}]})
        item = read['items'][0]
        self.assertEqual(item['status'], 'completed', read)
        rows = [{'kind': 'source-line', 'text': line['text'], 'location': {'line': line['line']},
                 'source': {'path': item['path'], 'revision': item['revision']}}
                for line in item['items']]
        return {'kind': 'evidence-packet', 'operation': 'investigate', 'status': 'completed',
                'evidenceState': 'collected', 'items': rows,
                'coverage': {'stages': [{'path': str(path)}]}}

    def remember(self, value=None, args=None):
        return workflow_memory.remember(self.store, str(self.root), OWNER,
                                        self.args if args is None else args, self.packet() if value is None else value)

    def test_exact_file_query_is_reauthorized_and_native_revision_checked(self):
        original = self.packet()
        before = copy.deepcopy(original)
        self.assertEqual(self.remember(original)['state'], 'saved')
        calls = []
        def observed(root, operation, args):
            calls.append(operation)
            return files.run(root, operation, args)
        hit = workflow_memory.reuse(self.store, str(self.root), OWNER, self.args, observed)
        self.assertTrue(hit['evidenceReuse']['hit'])
        self.assertEqual(calls, ['read'])
        self.assertEqual(hit['items'], original['items'])
        self.assertEqual(original, before)
        self.file.write_text('LIMIT = 999\n')
        self.assertIsNone(workflow_memory.reuse(self.store, str(self.root), OWNER, self.args, observed))

    def test_latest_resume_without_manual_save_checks_changes_and_scope(self):
        saved = self.remember()
        result = workflow_entry.run(self.store, str(self.root), OWNER, 'working_set', {'action': 'resume'})
        self.assertEqual(result['items'][0]['state'], 'current')
        self.assertIn('LIMIT = 17', json.dumps(result))
        self.file.write_text('LIMIT = 23\n')
        stale = workflow_entry.run(self.store, str(self.root), OWNER, 'working_set', {'action': 'resume'})
        self.assertEqual(stale['items'][0]['state'], 'stale')
        self.assertNotIn('LIMIT = 17', json.dumps(stale))
        other = {**OWNER, 'session': '01a18391-1809-7601-96cc-09b2c96329c2'}
        with session_scope.bind(other):
            denied = workflow_entry.run(self.store, str(self.root), other, 'working_set', {'action': 'resume'})
            self.assertEqual(denied['status'], 'error')
            explicit = workflow_entry.run(self.store, str(self.root), other, 'working_set',
                                          {'action': 'resume', 'workingSetRef': saved['workingSetRef']})
            self.assertEqual(explicit['status'], 'error')
        self.assertEqual(workflow_entry.run(self.store, str(self.root / 'missing'), OWNER,
                                            'working_set', {'action': 'resume'})['status'], 'error')

    def test_stale_resume_returns_fresh_evidence_from_one_unchanged_native_read(self):
        saved = self.remember()
        manifest_before = copy.deepcopy(self.store.get(saved['workingSetRef']))
        self.file.write_text('LIMIT = 23\n')
        calls = []
        def observed(root, operation, args):
            result = files.run(root, operation, args)
            calls.append((result, copy.deepcopy(result)))
            return result
        result = workflow_entry.run(self.store, str(self.root), OWNER, 'working_set',
                                    {'action': 'resume'}, invoke=observed)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], calls[0][1])
        item = result['items'][0]
        self.assertEqual(item['state'], 'stale')
        self.assertNotEqual(item['revision'], item['currentRevision'])
        self.assertEqual(item['currentEvidence']['revision'], item['currentRevision'])
        self.assertEqual(item['currentEvidence']['items'][0]['text'], 'LIMIT = 23')
        self.assertNotIn('LIMIT = 17', json.dumps(result))
        self.assertEqual(self.store.get(saved['workingSetRef']), manifest_before)

    def test_changed_late_source_returns_window_around_saved_location(self):
        lines = ['# context'] * 200
        lines[119] = 'LIMIT = 77'
        self.file.write_text('\n'.join(lines) + '\n')
        packet = self.packet()
        packet['items'] = [{**packet['items'][0], 'text': 'LIMIT = 77', 'location': {'line': 120}}]
        self.remember(packet)
        lines[119] = 'LIMIT = 91'
        self.file.write_text('\n'.join(lines) + '\n')
        result = workflow_entry.run(self.store, str(self.root), OWNER, 'working_set', {'action': 'resume'})
        current = result['items'][0]['currentEvidence']
        self.assertEqual(current['requestedWindow'], {'offset': 118, 'limit': 5})
        self.assertIn({'line': 120, 'path': str(self.file), 'text': 'LIMIT = 91'}, current['items'])
        self.assertLessEqual(len(current['items']), 64)
        self.assertNotIn('LIMIT = 77', json.dumps(result))
        self.assertFalse(current['complete'])

    def test_oversized_fresh_window_is_retrievable_without_rereading_file(self):
        self.remember()
        fresh = 'FRESH = ' + 'x' * 6000
        self.file.write_text(fresh + '\n')
        result = workflow_entry.run(self.store, str(self.root), OWNER, 'working_set',
                                    {'action': 'resume', 'maxBytes': 2048})
        item = result['items'][0]
        self.assertTrue(item['currentEvidenceOmitted'])
        self.assertNotIn('currentEvidence', item)
        self.assertNotEqual(item['currentEvidenceRef'], item['ref'])
        self.file.unlink()
        recovered = self.store.get(item['currentEvidenceRef'])
        self.assertEqual(recovered['revision'], item['currentRevision'])
        self.assertEqual(recovered['items'][0]['text'], fresh)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False).encode()), 2048)

    def test_unknown_locations_use_bounded_head_and_no_fake_retrieval_reference(self):
        source = {'path': str(self.file)}
        for value in ('text', {'items': None}, {'items': [None, {}, {'source': []},
                {'source': {'path': 'elsewhere'}, 'location': {'line': 900}},
                {'source': source, 'location': None},
                {'source': source, 'location': {'line': True}},
                {'source': source, 'location': {'line': -1}}]}):
            self.assertEqual(working_set_current.request(source, value),
                             {'path': str(self.file), 'offset': 1, 'limit': 64})
        item = {'currentEvidence': {'path': str(self.file), 'revision': 'new', 'items': [{'text': 'new'}]}}
        before = copy.deepcopy(item)
        omitted, budget = working_set_current.bounded(item, 0, None)
        self.assertEqual(budget, 0)
        self.assertTrue(omitted['currentEvidenceOmitted'])
        self.assertNotIn('currentEvidenceRef', omitted)
        self.assertEqual(item, before)

    def test_directory_queries_and_permission_changes_do_not_reuse(self):
        args = {'question': 'Where is LIMIT?'}
        self.remember(args=args)
        self.assertIsNone(workflow_memory.reuse(self.store, str(self.root), OWNER, args, files.run))
        self.remember()
        changed = {**OWNER, 'policy': 'read-only'}
        with session_scope.bind(changed):
            self.assertIsNone(workflow_memory.reuse(self.store, str(self.root), changed, self.args, files.run))
        self.assertEqual(workflow_memory.remember(self.store, str(self.root), {}, self.args, self.packet())['state'],
                         'unattributed-or-empty')
        self.assertIsNone(workflow_memory.reuse(self.store, str(self.root), {}, self.args, files.run))

    def test_per_source_snapshots_do_not_label_another_files_stale_lines_current(self):
        second = self.root / 'other.py'
        second.write_text('OTHER = 31\n')
        combined = self.packet()
        combined['items'].extend(self.packet(second)['items'])
        self.remember(combined)
        second.write_text('OTHER = 99\n')
        result = workflow_entry.run(self.store, str(self.root), OWNER, 'working_set', {'action': 'resume'})
        self.assertEqual([row['state'] for row in result['items']], ['current', 'stale'])
        self.assertNotIn('OTHER = 31', json.dumps(result))
        self.assertIn('LIMIT = 17', json.dumps(result))

    def test_expired_references_and_unwritable_memory_do_not_reuse(self):
        self.remember()
        self.store.ttl = -1
        self.assertIsNone(workflow_memory.reuse(self.store, str(self.root), OWNER, self.args, files.run))
        self.store.ttl = 86400
        with self.store.db:
            self.store.db.execute('DELETE FROM observations')
        self.assertIsNone(workflow_memory.reuse(self.store, str(self.root), OWNER, self.args, files.run))
        self.store.db.execute('PRAGMA query_only=ON')
        self.assertEqual(self.remember()['state'], 'unavailable')

    def test_entry_defaults_and_invalid_requests(self):
        self.assertEqual(workflow_entry.arguments('investigate', None, 'Where is LIMIT?'), {'question': 'Where is LIMIT?'})
        for operation, args, question in [('verify', {}, 'x'), ('investigate', {'question': 'x'}, 'y'), ('investigate', [], None)]:
            with self.assertRaises(ValueError):
                workflow_entry.arguments(operation, args, question)
        self.assertEqual(workflow_entry.run(self.store, str(self.root), OWNER, 'verify', [])['status'], 'error')

    def test_lexical_dot_path_recovers_after_native_approved_canonical_read(self):
        packet = self.packet()
        lexical = str(self.root) + os.sep + '.' + os.sep + 'limits.py'
        for row in packet['items']:
            row['source']['path'] = lexical
        self.remember(packet)
        resumed = workflow_entry.run(self.store, str(self.root), OWNER, 'working_set', {'action': 'resume'})
        self.assertEqual(resumed['items'][0]['state'], 'current', resumed)
        self.assertIn('LIMIT = 17', json.dumps(resumed))
        self.file.write_text('LIMIT = 71\n')
        stale = workflow_entry.run(self.store, str(self.root), OWNER, 'working_set', {'action': 'resume'})
        self.assertEqual(stale['items'][0]['state'], 'stale')
        self.assertNotIn('LIMIT = 17', json.dumps(stale))

    def test_same_content_other_file_and_invalid_metadata_do_not_attest_source(self):
        other = self.root / 'other.py'
        other.write_text(self.file.read_text())
        packet = self.packet(other)
        ref = self.store.capture(packet, force=True)['ref']
        revision = packet['items'][0]['source']['revision']
        denied = workflow_entry.run(self.store, str(self.root), OWNER, 'working_set',
            {'action': 'save', 'sources': [{'ref': ref, 'path': 'limits.py', 'revision': revision}]})
        self.assertEqual(denied['status'], 'error')
        self.assertFalse(working_set_sources._matches({'path': None, 'revision': revision}, str(self.file), revision))
        self.assertFalse(working_set_sources._matches([], str(self.file), revision))

    def test_automatic_anchor_extraction_avoids_common_prose_but_explicit_anchors_are_literal(self):
        query = investigate_query.parse({'question': 'Where is the function that caps retry delay?'})
        self.assertEqual(query['anchors'], ['retry', 'delay'])
        explicit = investigate_query.parse({'question': 'Find this literal', 'anchors': ['the', 'caps']})
        self.assertEqual(explicit['anchors'], ['the', 'caps'])
        self.assertEqual(investigate_query.parse({'question': 'cap'})['anchors'], ['cap'])


class NativeObservationTests(unittest.TestCase):
    def test_automatic_display_preserves_failure_and_exact_original_without_verify_call(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'CODEX_OPS_STORE': directory}):
            original = {'exit_code': 9, 'output': ('INFO progress ' + 'x' * 80 + '\n') * 400 + 'ERROR final failure',
                        'chunk_id': 'observed-failure', 'isError': False}
            emitted = json.dumps(original)
            displayed = json.loads(Presenter().render(emitted))
            self.assertEqual(displayed['metadata']['exit_code'], 9)
            self.assertIn('final failure', json.dumps(displayed))
            self.assertLess(len(json.dumps(displayed)), len(emitted) // 4)
            with closing(Store(directory)) as store:
                self.assertEqual(store.get(displayed['ref']), emitted)
            self.assertEqual(json.dumps(original), emitted)

    def test_failure_is_inferred_from_exit_not_error_words_or_envelope_flag(self):
        value = {'output': 'INFO started\n' * 1000 + 'ERROR tail failure\n', 'exit_code': 7, 'isError': False}
        original = copy.deepcopy(value)
        result = native_observation_view.preview(structured.analyze(value))
        self.assertEqual(result['executionState'], 'failed')
        self.assertEqual(result['exit_code'], 7)
        self.assertEqual(result['diagnostics'][0]['line'], 1001)
        self.assertEqual(value, original)
        success = native_observation_view.preview(structured.analyze({'output': 'ERROR expected fixture', 'exit_code': 0}))
        self.assertEqual(success['executionState'], 'completed')

    def test_running_unknown_media_and_diagnostic_bounds(self):
        running = native_observation_view.preview(structured.analyze({'output': '', 'session_id': 17}))
        self.assertEqual(running['executionState'], 'running')
        self.assertEqual(running['session_id'], 17)
        self.assertIn('existing native session', running['nextAction'])
        unknown = native_observation_view.preview(structured.analyze({'output': '', 'chunk_id': 'x'}))
        self.assertEqual(unknown['executionState'], 'unknown')
        for value in ['hello', {'output': 'text'}, {'content': [{'type': 'image', 'data': 'abc'}]}]:
            self.assertIsNone(native_observation_view.preview(structured.analyze(value)))
        verbose = {'output': ('ERROR ' + 'x' * 400 + '\n') * 10, 'exit_code': 1}
        result = native_observation_view.preview(structured.analyze(verbose))
        self.assertEqual(result['omittedDiagnostics'], 4)
        self.assertEqual(len(result['diagnostics']), 6)
        self.assertTrue(all(row['clipped'] for row in result['diagnostics']))


if __name__ == '__main__':
    unittest.main()
