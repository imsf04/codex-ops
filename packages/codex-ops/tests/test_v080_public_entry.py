"""Public entry uses the real Rust kernel and automatically rechecks saved evidence."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import cost_events
import server

CHAT = '01a18391-1809-7601-96cc-09b2c96329c1'


def unpack(result):
    return result['value'] if result.get('kind') == 'inline' else result


class PublicEntryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.file = self.root / 'limits.py'
        self.file.write_text('LIMIT = 17\ndef cap(n):\n    return min(n, LIMIT)\n')
        self.environment = patch.dict(os.environ, {'CODEX_OPS_STORE': str(self.root / 'cache'),
                                                  'CODEX_OPS_MEASUREMENT_ORIGIN': 'validation'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.ctx = SimpleNamespace(request_context=SimpleNamespace(meta={'threadId': CHAT}))

    def investigate(self):
        return unpack(server.ops_workflow(str(self.root), question='Where is LIMIT used?',
                                          args={'paths': ['limits.py']}, ctx=self.ctx))

    def test_root_question_entry_reuses_fresh_sources_and_recovers_without_a_save_call(self):
        first = self.investigate()
        self.assertEqual(first['evidenceState'], 'collected', first)
        self.assertEqual(first['workingSet']['state'], 'saved')
        second = self.investigate()
        self.assertTrue(second['evidenceReuse']['hit'], second)
        self.assertEqual(first['items'], second['items'])
        measured = cost_events.snapshot('chat:' + CHAT, origin='validation')
        self.assertEqual(measured['workerStarts'], 2, measured)
        self.assertTrue(any(row['operation'] == 'working_set' and row['reused'] for row in measured['groups']))
        resumed = unpack(server.ops_workflow(str(self.root), 'working_set', {'action': 'resume'}, self.ctx))
        self.assertEqual(resumed['items'][0]['state'], 'current')
        self.assertIn('LIMIT = 17', json.dumps(resumed))
        self.file.write_text('LIMIT = 39\n')
        stale = unpack(server.ops_workflow(str(self.root), 'working_set', {'action': 'resume'}, self.ctx))
        self.assertEqual(stale['items'][0]['state'], 'stale')
        self.assertNotIn('LIMIT = 17', json.dumps(stale))
        refreshed = self.investigate()
        self.assertNotIn('evidenceReuse', refreshed)
        self.assertIn('LIMIT = 39', json.dumps(refreshed))

    def test_entry_rejects_ambiguous_parameters_and_other_chat_recovery(self):
        invalid = server.ops_workflow(str(self.root), question='one', args={'question': 'two'}, ctx=self.ctx)
        self.assertEqual(invalid['error']['code'], 'WORKFLOW_REJECTED')
        other = SimpleNamespace(request_context=SimpleNamespace(meta={'threadId': CHAT[:-1] + '2'}))
        self.investigate()
        missing = unpack(server.ops_workflow(str(self.root), 'working_set', {'action': 'resume'}, other))
        self.assertEqual(missing['status'], 'error')
        legacy = unpack(server.ops_workflow(str(self.root), 'investigate',
                                           {'question': 'Where is LIMIT?', 'paths': ['limits.py']}, self.ctx))
        self.assertEqual(legacy['evidenceState'], 'collected')

    def test_direct_file_reads_also_attribute_worker_starts_to_the_native_chat(self):
        result = unpack(server.ops_files(str(self.root), 'read',
                        {'files': [{'path': 'limits.py', 'limit': 3}]}, self.ctx))
        self.assertEqual(result['status'], 'completed')
        measured = cost_events.snapshot('chat:' + CHAT, origin='validation')
        self.assertEqual(measured['workerStarts'], 1)


if __name__ == '__main__':
    unittest.main()
