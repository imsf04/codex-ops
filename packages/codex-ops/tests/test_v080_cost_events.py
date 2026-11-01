import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

import cost_events
import observation_metrics
import task_cost
import task_cost_cohorts
import task_cost_records
import task_cost_workflows

CHAT = 'chat:11111111-1111-1111-1111-111111111111'


class CostEventTests(unittest.TestCase):
    def test_actual_starts_are_separate_from_workflows_and_cohorts(self):
        with tempfile.TemporaryDirectory() as directory:
            with cost_events.scope(CHAT, 'C:/example', 'task-1'):
                self.assertTrue(cost_events.worker('grep', root=directory, now=10, origin='validation'))
                self.assertTrue(cost_events.record('workflow', 'investigate', 'partial', 'present', True,
                                                  root=directory, now=11, origin='validation'))
            cost_events.worker('read', root=directory, now=12, origin='production')
            result = cost_events.snapshot(CHAT, directory, since=10, until=12, origin='validation',
                                          version=cost_events.VERSION)
            self.assertEqual(result['workerStarts'], 1)
            self.assertEqual(sum(row['count'] for row in result['groups']), 2)
            self.assertIsNone(result['adoptionRate'])
            self.assertEqual(cost_events.snapshot(CHAT, directory)['workerStarts'], 0)
            self.assertEqual(cost_events.snapshot(None, directory)['workerStarts'], 1)
            raw = (Path(directory)/'task-events.sqlite3').read_bytes()
            self.assertNotIn(b'C:/example', raw)
            self.assertNotIn(CHAT.encode(), raw)
            self.assertNotIn(b'task-1', raw)

    def test_missing_invalid_or_unavailable_ledger_is_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            before = cost_events.WRITE_FAILURES
            self.assertFalse(cost_events.snapshot(CHAT, directory)['available'])
            self.assertFalse(cost_events.snapshot('runtime:123', directory)['available'])
            bad = Path(directory)/'blocked'
            bad.write_text('file')
            self.assertFalse(cost_events.worker('read', root=bad))
            (Path(directory)/'task-events.sqlite3').write_bytes(b'not a sqlite database')
            self.assertFalse(cost_events.snapshot(CHAT, directory)['available'])
            self.assertFalse(cost_events.worker('read', root=directory))
            collection = cost_events.snapshot(CHAT, directory)['collection']
            self.assertEqual(collection['knownDroppedEvents'], before+2)
            self.assertFalse(collection['complete'])

    def test_retention_unknown_labels_and_scope_restoration(self):
        with tempfile.TemporaryDirectory() as directory:
            with cost_events.scope(CHAT, 'C:/first'):
                with cost_events.scope('unknown', 'C:/second'):
                    cost_events.worker('private body not a tool', root=directory, now=1, origin='invalid')
                cost_events.worker('read', root=directory, now=2, origin='validation')
            self.assertEqual(cost_events.CURRENT.get(), (None, None, None))
            unknown = cost_events.snapshot(None, directory, origin='invalid')
            self.assertEqual(unknown['groups'][0]['operation'], 'unknown')
            self.assertEqual(cost_events.snapshot(CHAT, directory, origin='validation')['workerStarts'], 1)
            cost_events.worker('read', root=directory, now=31*86400, origin='validation')
            self.assertEqual(cost_events.snapshot(None, directory, origin='validation')['workerStarts'], 1)

    def test_automatic_save_is_recorded_but_not_counted_as_served(self):
        import v080_metrics
        with tempfile.TemporaryDirectory() as directory:
            with cost_events.scope(CHAT, 'C:/fixture'):
                cost_events.record('automatic','working_set.save','completed','present',root=directory,origin='validation')
            rows = cost_events.snapshot(CHAT,directory,origin='validation')['groups']
            self.assertEqual(rows[0]['operation'],'working_set.save')
            adoption = v080_metrics.adoption([], 'holdout_changed_resume', rows)
            self.assertEqual(adoption['automaticSaves'],1)
            self.assertFalse(adoption['automaticallyServed'])
            with cost_events.scope(CHAT, 'C:/fixture'):
                cost_events.record('automatic','working_set','completed','present',reused=True,root=directory,origin='validation')
            rows = cost_events.snapshot(CHAT,directory,origin='validation')['groups']
            self.assertTrue(v080_metrics.adoption([], 'holdout_changed_resume', rows)['automaticallyServed'])

    def test_evidence_is_independent_of_transport_completion(self):
        self.assertEqual(task_cost_workflows.operation({'arguments':{'question':'Where is the limit?'}}),'investigate')
        self.assertEqual(task_cost_workflows.operation({'arguments':{}}),'unknown')
        self.assertEqual(task_cost_workflows.operation({'arguments':{'operation':'verify','question':'ignored'}}),'verify')
        self.assertEqual(task_cost_workflows.assess({'status':'completed'})['evidence'], 'unknown')
        self.assertEqual(task_cost_workflows.assess({'status':'rejected'})['outcome'], 'failed')
        self.assertEqual(task_cost_workflows.assess({'evidenceState':'no_match'})['evidence'], 'absent')
        self.assertEqual(task_cost_workflows.assess({'evidenceState':'collected','items':[{'text':'source'}]})['evidence'], 'present')
        self.assertEqual(task_cost_workflows.assess({'operation':'verify','exitCode':0})['evidence'], 'present')
        self.assertEqual(task_cost_workflows.assess({'operation':'verify','exitCode':None})['evidence'], 'unknown')
        self.assertEqual(task_cost_workflows.assess({'diagnostics':[{'line':3}]})['evidence'], 'present')
        self.assertTrue(task_cost_workflows.assess({'evidenceReuse':{'hit':True}})['reused'])
        self.assertEqual(task_cost_workflows.assess({'evidenceState':'collected','items':[{'text':'  '}]})['evidence'], 'unknown')
        documents = {'operation':'documents','items':[{'evidence':{'items':[{'row':{'value':0}}]}}]}
        self.assertEqual(task_cost_workflows.assess(documents)['evidence'], 'present')
        self.assertEqual(task_cost_workflows.assess({'operation':'documents','items':[]})['evidence'], 'absent')

    def test_workflow_observation_keeps_values_and_records_real_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = os.environ.get('CODEX_OPS_STORE')
            os.environ['CODEX_OPS_STORE'] = directory
            try:
                value = {'status':'partial','evidenceState':'collected','items':[{'text':'source'}]}
                self.assertIs(observation_metrics.workflow(value, 'investigate', CHAT, 'C:/workspace'), value)
                result = cost_events.snapshot(CHAT, directory)
                self.assertEqual(result['groups'][0]['evidence'], 'present')
            finally:
                if previous is None:
                    os.environ.pop('CODEX_OPS_STORE')
                else:
                    os.environ['CODEX_OPS_STORE'] = previous

    def test_cohorts_reject_unassigned_times_and_preserve_turns(self):
        rows = [{'timestamp':'2026-10-30T01:00:00Z','_turnId':'first'},
                {'timestamp':'2026-10-30T02:00:00Z','_turnId':'second'},
                {'timestamp':'bad','_turnId':'second'}, {'_turnId':'second'}]
        selected, receipt = task_cost_cohorts.select(rows, since='2026-10-30T01:00:00Z',
                                                   until='2026-10-30T02:00:00Z')
        self.assertEqual(selected, rows[:1])
        self.assertEqual(receipt['excludedRecords'], 3)
        self.assertEqual(task_cost_cohorts.select(rows, turn_id='second')[0], rows[1:])
        self.assertEqual(task_cost_cohorts.select(rows, since=0, turn_id='first')[0], rows[:1])
        for value in (True, float('nan'), {}, '2026-10-30T01:00:00'):
            with self.assertRaises((ValueError, TypeError)):
                task_cost_cohorts.boundary(value)
        with self.assertRaises(ValueError):
            task_cost_cohorts.select(rows, since=3, until=3)

    def test_local_rollout_turn_cohort_uses_recorded_identity(self):
        session = CHAT.removeprefix('chat:')
        rows = [{'type':'session_meta','payload':{'id':session}},
                {'type':'turn_context','payload':{'turn_id':'first'}},
                {'type':'token_usage_record','timestamp':'2026-10-30T01:00:00Z',
                 'payload':{'response_id':'r1','usage':{'input_tokens':10}}},
                {'type':'turn_context','payload':{'id':'second'}},
                {'type':'token_usage_record','timestamp':'2026-10-30T02:00:00Z',
                 'payload':{'response_id':'r2','usage':{'input_tokens':20}}}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/('rollout-'+session+'.jsonl')
            path.write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
            parsed = task_cost_records.read([path])
            self.assertEqual(parsed[-1]['_turnId'], 'second')
            result = task_cost.report(CHAT, directory, turn_id='second')
            self.assertEqual(result['tokens']['input_tokens'], 20)
            self.assertEqual(result['selection']['turnId'], 'second')
            self.assertFalse(task_cost.report(CHAT, directory, since=2, until=1)['available'])


if __name__ == '__main__':
    unittest.main()
