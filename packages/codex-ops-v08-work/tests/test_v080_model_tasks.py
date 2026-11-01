import base64
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import run_v080_costs as runner
import v080_metrics as metrics
import v080_model_tasks as tasks


class AcceptanceTests(unittest.TestCase):
    def test_screen_schedule_preserves_full_schedule_and_repeats_every_pair(self):
        full = runner.schedule()
        screen = runner.selected_schedule(screen='friction18')
        self.assertEqual(len(screen),18)
        counts = Counter((r['task'],r['condition']) for r in screen)
        self.assertEqual(set(counts.values()),{3})
        self.assertEqual(len(counts),6)
        expanded = runner.selected_schedule(screen='friction20')
        self.assertEqual(len(expanded),20)
        terminal = [r for r in expanded if r['task']=='holdout_terminal_failure']
        self.assertEqual({(r['condition'],r['repeat']) for r in terminal},{('v070',1),('v080',1)})
        self.assertEqual(runner.schedule(),full)
        self.assertEqual(len(runner.selected_schedule()),132)

    def test_adoption_reads_completed_result_after_started_event(self):
        item = {'id':'workflow1','type':'mcpToolCall','tool':'ops_workflow',
                'arguments':{'operation':'investigate'}}
        payload = {'kind':'inline','value':{'status':'completed','evidenceState':'collected',
                   'items':[{'kind':'source-line','text':'return min(delay, 45)'}]}}
        completed = {**item,'result':{'content':[{'type':'text','text':json.dumps(payload)}]}}
        events = [{'method':'item/started','params':{'item':item}},
                  {'method':'item/completed','params':{'item':completed}},
                  {'method':'item/completed','params':{'item':completed}}]
        result = metrics.adoption(events,'code_location')
        self.assertEqual(result['selectedOperations'],{'investigate':1})
        self.assertEqual(result['evidence'],{'present':1})
        self.assertEqual(metrics.adoption(events[:1],'code_location')['evidence'],{'unknown':1})

    def test_plan_is_balanced_and_opportunities_are_independent(self):
        schedule = runner.schedule()
        self.assertEqual(len(schedule),132)
        self.assertEqual(len({r['key'] for r in schedule}),132)
        self.assertEqual(Counter(r['condition'] for r in schedule), {'v061':36,'v070':48,'v080':48})
        self.assertEqual(set(tasks.OPPORTUNITIES),set(tasks.TASKS))
        plan = subprocess.run([sys.executable,str(Path(runner.__file__))],capture_output=True,
                              text=True,encoding='utf-8',check=True)
        self.assertEqual(json.loads(plan.stdout)['paidCalls'],0)

    def test_holdout_outcomes_require_correct_evidence_and_preserved_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in tasks.HOLDOUT:
                if name == 'holdout_terminal_failure':
                    continue
                root = Path(directory)/name
                expected = tasks.prepare_task(name,root)
                self.assertFalse(tasks.evaluate_task(name,root,expected)['passed'])
                for path,value in expected.get('phaseChange',{}).items():
                    (root/path).write_bytes(value.encode())
                tasks.solve_for_self_test(name,root,expected)
                self.assertTrue(tasks.evaluate_task(name,root,expected)['passed'],name)
                (root/'answer.json').write_text('{}')
                self.assertFalse(tasks.evaluate_task(name,root,expected)['passed'])

    def test_actual_holdout_producer_has_terminal_exit_and_exact_lf_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'task'
            expected = tasks.prepare_task('holdout_terminal_failure',root)
            result = subprocess.run([sys.executable,'-I',str(root/'run_terminal.py')],cwd=root,
                                    capture_output=True,text=True,timeout=25)
            self.assertEqual(result.returncode,9)
            self.assertIn('ERROR HOLDOUT_FORMAT',result.stdout)
            self.assertEqual((root/'terminal.receipt').read_bytes(),b'finished-exit-9\n')
            tasks.solve_for_self_test('holdout_terminal_failure',root,expected)
            payload = base64.b64encode(json.dumps(expected).encode()).decode()
            oracle = subprocess.run([sys.executable,'-I',str(Path(runner.ROOT)/'tests/native_v080_oracle.py'),
                '--task','holdout_terminal_failure','--root',str(root),'--expected',payload],
                capture_output=True,text=True,check=True)
            self.assertTrue(json.loads(oracle.stdout)['passed'])
            events = [{'method':'item/completed','params':{'item':{'type':'commandExecution','command':'python run_terminal.py','exitCode':9}}}]
            self.assertTrue(tasks.execution_observed(events,expected))
            self.assertTrue(tasks.execution_exit_observed(events,expected))
            events[0]['params']['item']['exitCode'] = 1
            self.assertTrue(tasks.execution_observed(events,expected))
            self.assertFalse(tasks.execution_exit_observed(events,expected))
            self.assertFalse(tasks.execution_observed([],expected))

    def test_worker_unknown_is_not_reported_as_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(metrics.measured_workers(directory)['starts'])
            path = Path(directory)/'mcp-worker-starts.jsonl'
            path.write_text('{')
            self.assertFalse(metrics.measured_workers(directory)['available'])
            path.write_text('{"kind":"observer-ready"}\n{"kind":"worker-start"}\n')
            self.assertEqual(metrics.measured_workers(directory)['starts'],1)

    def test_adoption_does_not_equate_completion_with_useful_evidence(self):
        item = {'type':'mcpToolCall','id':'one','tool':'ops_workflow',
                'arguments':{'operation':'investigate'},'status':'completed',
                'result':{'structuredContent':{'kind':'inline','value':{'evidenceState':'no_match'}}}}
        events = [{'params':{'item':item}}]*2
        result = metrics.adoption(events,'holdout_code_test_config')
        self.assertTrue(result['selectedEligibleWorkflow'])
        self.assertEqual(result['selectedOperations'],{'investigate':1})
        self.assertEqual(result['evidence'],{'absent':1})
        self.assertFalse(result['automaticallyServed'])
        self.assertEqual(metrics.gates({}, {}, False)['status'],'INCOMPLETE')


if __name__ == '__main__':
    unittest.main()
