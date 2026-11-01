import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evidence_index
import evidence_index_query
import evidence_index_rows
import evidence_index_budget
import session_scope
from store import Store
import working_set
import working_set_sources


class EvidenceTests(unittest.TestCase):
    def test_cross_reference_opposing_evidence_and_exact_pointer(self):
        values = {'a': {'policy': 'Policy allows refunds'}, 'b': {'policy': 'Policy forbids refunds'}}
        result = evidence_index.run('.', {'refs': ['a', 'b'], 'query': 'refunds'}, 'chat', load=values.__getitem__)
        self.assertEqual({row['ref'] for row in result['items']}, {'a', 'b'})
        self.assertEqual({row['pointer'] for row in result['items']}, {'/policy'})
        self.assertEqual({row['text'] for row in result['items']}, {value['policy'] for value in values.values()})
        self.assertTrue(result['scanComplete'])

    def test_permissions_expiry_rechecked_without_stale_index(self):
        values = {'a': 'needle allowed', 'b': 'needle other'}
        args = {'refs': ['a', 'b'], 'query': 'needle'}
        first = evidence_index.run('.', args, 'chat', load=values.__getitem__)
        self.assertEqual(len(first['items']), 2)
        del values['b']
        second = evidence_index.run('.', args, 'chat', load=values.__getitem__)
        self.assertEqual([row['ref'] for row in second['items']], ['a'])
        self.assertEqual(second['status'], 'partial')
        self.assertEqual(second['sources'][1]['status'], 'unavailable')

    def test_json_pointers_scalar_nodes_and_utf8_budget(self):
        rows, coverage = evidence_index_rows.flatten({'a/b~': ['错误 needle', 3, None]})
        self.assertEqual(rows[0]['pointer'], '/a~1b~0/0')
        self.assertTrue(coverage['scanComplete'])
        self.assertEqual(evidence_index_query.ranked(rows, '错误', 2), rows)
        with patch.object(evidence_index_rows, 'MAX_BYTES', 4):
            rows, coverage = evidence_index_rows.flatten('错误日志')
        self.assertEqual(rows[0]['text'], '错')
        self.assertFalse(coverage['scanComplete'])

    def test_node_limit_and_empty_source(self):
        with patch.object(evidence_index_rows, 'MAX_NODES', 2):
            rows, coverage = evidence_index_rows.flatten(['one', 'two'])
        self.assertFalse(coverage['scanComplete'])
        self.assertEqual(len(rows), 1)
        self.assertEqual(evidence_index_query.ranked([], 'needle', 2), [])
        result = evidence_index.run('.', {'refs': ['a'], 'query': 'missing'}, 'chat', load=lambda ref: 'unrelated')
        self.assertEqual(result['evidenceState'], 'no_match')

    def test_selection_limit_and_budget_never_claim_complete(self):
        values = {'a': ['needle ' + 'x' * 990] * 4}
        result = evidence_index.run('.', {'refs': ['a'], 'query': 'needle', 'maxBytes': 2500}, 'chat', load=values.__getitem__)
        self.assertEqual(len(result['items']), 1)
        self.assertFalse(result['selectionComplete'])
        result = evidence_index.run('.', {'refs': ['a'], 'query': 'needle', 'limit': 1}, 'chat', load=values.__getitem__)
        self.assertEqual(len(result['items']), 1)
        self.assertFalse(result['selectionComplete'])

    def test_literal_query_not_fts_expression(self):
        rows = [{'text': 'alpha beta'}]
        self.assertEqual(evidence_index_query.ranked(rows, 'alpha OR "beta"', 2), rows)
        for query in ['***', ' '.join('term' + str(i) for i in range(33))]:
            with self.assertRaises(ValueError): evidence_index_query.terms(query)

    def test_invalid_arguments(self):
        for args in [{'refs': [], 'query': 'x'}, {'refs': ['a', 'a'], 'query': 'x'},
                     {'refs': ['a'], 'query': 'x', 'bogus': 1}, {'refs': ['a'], 'query': 'x', 'limit': 0}]:
            with self.assertRaises(ValueError): evidence_index.run('.', args, 'chat', load=lambda ref: '')

    def test_whole_packet_budget_with_large_metadata(self):
        value = {'path': 'p' * 5000, 'items': ['needle ' * 400]}
        result = evidence_index.run('.', {'refs': ['a'], 'query': 'needle', 'maxBytes': 1024}, 'chat', load=lambda ref: value)
        self.assertLessEqual(evidence_index_budget.size(result), 1024)
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(result['omitted'])

    def test_budget_metadata_rejection(self):
        with self.assertRaises(ValueError): evidence_index_budget.bounded({'fixed': 'x' * 2000}, 1024)


class WorkingSetTests(unittest.TestCase):
    def setUp(self):
        self.values = {'source': {'items': [{'text': 'original exact evidence'}]}}
        self.revision = 'r1'

    def save(self, value):
        self.values['snapshot'] = json.loads(json.dumps(value))
        return 'snapshot'

    def invoke(self, root, operation, args):
        return {'items': [{'status': 'completed', 'revision': self.revision,
                           'path': str((Path(root) / 'app.py').resolve())}]}

    def call(self, args, context='chat', root='root'):
        return working_set.run(root, args, context, invoke=self.invoke,
                               load=self.values.__getitem__, save=self.save)

    def record(self, file=False):
        source = {'ref': 'source', 'label': 'known evidence'}
        if file:
            source.update(path='app.py', revision='r1')
            self.values['source'].update(path=str(Path('root/app.py').resolve()), revision='r1')
        return self.call({'action': 'save', 'sources': [source], 'pending': ['verify behavior']})

    def test_roundtrip_after_serialized_manifest_and_no_payload_copy(self):
        self.record()
        self.assertNotIn('value', self.values['snapshot']['sources'][0])
        result = self.call({'action': 'resume', 'workingSetRef': 'snapshot'})
        self.assertEqual(result['items'][0]['result'], self.values['source'])
        self.assertEqual(result['items'][0]['state'], 'saved-observation')
        self.assertFalse(result['contextRetentionAssumed'])
        self.assertEqual(result['pending'], ['verify behavior'])

    def test_source_revision_changed_does_not_emit_old_evidence(self):
        self.record(file=True)
        self.revision = 'r2'
        result = self.call({'action': 'resume', 'workingSetRef': 'snapshot'})
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['items'][0]['state'], 'stale')
        self.assertNotIn('result', result['items'][0])

    def test_file_revision_current(self):
        self.record(file=True)
        result = self.call({'action': 'resume', 'workingSetRef': 'snapshot'})
        self.assertEqual(result['items'][0]['state'], 'current')

    def test_scope_root_expiry_and_changed_observation(self):
        self.record()
        for options in [{'context': 'other'}, {'root': 'other'}]:
            with self.assertRaises(ValueError): self.call({'action': 'resume', 'workingSetRef': 'snapshot'}, **options)
        self.values['source'] = 'changed'
        result = self.call({'action': 'resume', 'workingSetRef': 'snapshot'})
        self.assertEqual(result['items'][0]['state'], 'unavailable')
        del self.values['source']
        result = self.call({'action': 'resume', 'workingSetRef': 'snapshot'})
        self.assertEqual(result['items'][0]['state'], 'unavailable')

    def test_budget_omission_with_explicit_ref(self):
        self.values['source'] = 'x' * 3000
        self.record()
        result = self.call({'action': 'resume', 'workingSetRef': 'snapshot', 'maxBytes': 2048})
        self.assertTrue(result['items'][0]['contentOmitted'])
        self.assertEqual(result['items'][0]['retrieveRef'], 'source')
        self.assertEqual(result['status'], 'partial')

    def test_invalid_save_and_snapshot(self):
        for args in [{'action': 'bad'}, {'action': 'save', 'sources': []},
                     {'action': 'save', 'sources': [{'ref': 'source', 'revision': 'r'}]},
                     {'action': 'save', 'sources': [{'ref': 'source'}], 'pending': ['a'] * 17},
                     {'action': 'resume', 'workingSetRef': 'source'}]:
            with self.assertRaises(ValueError): self.call(args)
        del self.values['source']
        with self.assertRaises(ValueError): self.record()

    def test_revision_missing_or_failed_never_saved(self):
        for value in [{'items': []}, {'items': [{'status': 'failed'}]}, {'items': [{'status': 'completed'}]},
                      {'items': [{'status': 'completed', 'revision': 'r1'}]}]:
            with patch.object(self, 'invoke', return_value=value):
                with self.assertRaises(ValueError): self.record(file=True)

    def test_null_is_real_inline_evidence(self):
        self.values['source'] = None
        self.record()
        result = self.call({'action': 'resume', 'workingSetRef': 'snapshot'})
        self.assertIn('result', result['items'][0])
        self.assertIsNone(result['items'][0]['result'])

    def test_whole_resume_packet_budget_and_notes(self):
        self.call({'action': 'save', 'sources': [{'ref': 'source', 'label': 'L' * 500}],
                   'pending': ['note' * 200] * 16, 'title': 'title' * 200})
        result = self.call({'action': 'resume', 'workingSetRef': 'snapshot', 'maxBytes': 1024})
        self.assertLessEqual(evidence_index_budget.size(result), 1024)
        self.assertEqual(result['status'], 'partial')
        self.assertGreater(result['omitted']['pending'], 0)
        self.assertTrue(result['omitted']['title'])

    def test_reference_cannot_claim_an_unrelated_file_revision(self):
        source = {'ref': 'source', 'path': 'app.py', 'revision': 'r1'}
        with self.assertRaises(ValueError): self.call({'action': 'save', 'sources': [source]})
        self.values['source'] = {'path': str(Path('root/app.py').resolve()), 'revision': 'r1'}
        with patch.object(self, 'invoke', return_value={'items': [{'status': 'completed',
                          'revision': 'r1', 'path': str(Path('root/other.py').resolve())}]}):
            with self.assertRaises(ValueError): self.call({'action': 'save', 'sources': [source]})

    def test_origin_traversal_bound(self):
        self.assertFalse(working_set_sources._origin(['unrelated'] * 5000, 'app.py', 'r1'))


class NativeOwnershipTests(unittest.TestCase):
    def test_saved_manifest_survives_connection_restart_but_not_source_expiry(self):
        with tempfile.TemporaryDirectory() as root:
            owner = {'session': 'chat-a', 'policy': 'policy-a'}
            store = Store(root)
            with session_scope.bind(owner):
                source = store.capture('restart evidence', force=True)['ref']
                saved = working_set.run(root, {'action': 'save', 'sources': [{'ref': source}]},
                    'chat-a', load=store.get, save=lambda value: store.capture(value, force=True)['ref'])
            store.db.close()
            store = Store(root)
            try:
                with session_scope.bind(owner):
                    result = working_set.run(root, {'action': 'resume', 'workingSetRef': saved['workingSetRef']},
                                             'chat-a', load=store.get)
                    self.assertEqual(result['items'][0]['result'], 'restart evidence')
                    store.db.execute('UPDATE observations SET created=0 WHERE ref=?', (source,))
                    store.db.commit()
                    result = working_set.run(root, {'action': 'resume', 'workingSetRef': saved['workingSetRef']},
                                             'chat-a', load=store.get)
                    self.assertEqual(result['items'][0]['state'], 'unavailable')
                    self.assertNotIn('result', result['items'][0])
                with session_scope.bind({'session': 'chat-a', 'policy': 'new-policy'}):
                    result = evidence_index.run(root, {'refs': [saved['workingSetRef']], 'query': 'restart'},
                                                'chat-a', load=store.get)
                    self.assertEqual(result['items'], [])
            finally:
                store.db.close()

    def test_store_owner_revalidation_and_release(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            owner = {'session': 'chat-a', 'policy': 'policy-a', 'runtime': '1'}
            with session_scope.bind(owner):
                ref = store.capture('needle exact', force=True)['ref']
                result = evidence_index.run(root, {'refs': [ref], 'query': 'needle'}, 'context', load=store.get)
                self.assertEqual(result['items'][0]['text'], 'needle exact')
            with session_scope.bind({'session': 'chat-b', 'policy': 'policy-a'}):
                result = evidence_index.run(root, {'refs': [ref], 'query': 'needle'}, 'context', load=store.get)
                self.assertEqual(result['items'], [])
                self.assertEqual(result['evidenceState'], 'unavailable')
            with session_scope.bind(owner):
                store.result(ref, action='release')
                result = evidence_index.run(root, {'refs': [ref], 'query': 'needle'}, 'context', load=store.get)
                self.assertEqual(result['items'], [])
            store.db.close()


if __name__ == '__main__':
    unittest.main()
