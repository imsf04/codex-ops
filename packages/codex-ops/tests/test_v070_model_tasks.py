import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from v070_model_tasks import TASKS, prepare_task, evaluate_task, solve_for_self_test
from run_v070_costs import schedule, summarize, FAMILY_MAPPING, execution_observed, stop_at_pair_boundary, resume_report, ROOT, digest


class CostFixtureTests(unittest.TestCase):
    def test_twelve_independent_tasks_reject_unsolved_and_corruption(self):
        prompts=set()
        with tempfile.TemporaryDirectory() as directory:
            for task in TASKS:
                with self.subTest(task=task):
                    root=Path(directory)/task
                    expected=prepare_task(task,root)
                    prompts.add(expected['spec'])
                    self.assertNotIn('ops_',expected['spec'])
                    self.assertFalse(evaluate_task(task,root,expected)['passed'])
                    solve_for_self_test(task,root,expected)
                    self.assertTrue(evaluate_task(task,root,expected)['passed'])
                    protected=next(iter(expected['preserved']))
                    (root/protected).write_bytes(b'corrupted input')
                    self.assertFalse(evaluate_task(task,root,expected)['passed'])
        self.assertEqual(len(prompts),12)

    def test_answer_cannot_replace_required_mutation_or_execution_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            for task in ('source_revised_during_task','resume_partial_work','long_command_failure'):
                root=Path(directory)/task;expected=prepare_task(task,root)
                (root/'answer.json').write_text(json.dumps(expected['answer']))
                self.assertFalse(evaluate_task(task,root,expected)['passed'])
                solve_for_self_test(task,root,expected)
                self.assertTrue(evaluate_task(task,root,expected)['passed'])

    def test_wrong_scalar_types_and_source_text_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for task,key,value in [('configuration_order','selected',False),
                                   ('chinese_anchor','limit','4'),('medium_exact_source','source_text','approximately correct')]:
                root=Path(directory)/task;expected=prepare_task(task,root)
                wrong={**expected['answer'],key:value}
                (root/'answer.json').write_text(json.dumps(wrong))
                self.assertFalse(evaluate_task(task,root,expected)['passed'])

    def test_model_schedule_has_three_pairs_per_task_and_alternating_order(self):
        rows=schedule();self.assertEqual(len(rows),72)
        self.assertEqual(len({r['key'] for r in rows}),72)
        for task in TASKS:
            selected=[r for r in rows if r['task']==task]
            self.assertEqual(len(selected),6)
            self.assertEqual(sum(r['condition']=='v061' for r in selected),3)
        self.assertEqual(rows[0]['condition'],rows[3]['condition'])

    def test_failure_remains_in_totals_but_not_common_success(self):
        base={'task':'sample','repeat':1,'outcome':{'passed':True},'eligibleForComparison':True,
              'tokens':{'total':{'inputTokens':100,'cachedInputTokens':80}},'completedItemsByType':{'commandExecution':4}}
        old={**base,'condition':'v061'}
        new={**base,'condition':'v070','outcome':{'passed':False}}
        report=summarize([old,new])
        self.assertEqual(report['allAttempts']['v070']['inputTokens'],100)
        self.assertEqual(report['commonSuccessfulPairs']['v070']['attempts'],0)
        self.assertFalse(report['releaseGatePassed'])
        self.assertIsNone(report['targets']['presentationInducedRetrievalReduction'])

    def test_fabricated_receipt_does_not_prove_native_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'events.jsonl';path.write_text('')
            row={'task':'long_command_failure','eventsPath':str(path),'outcome':{'passed':True}}
            execution_observed(row);self.assertFalse(row['outcome']['passed'])
            event={'method':'item/completed','params':{'item':{'type':'commandExecution','command':'python run_probe.py','exitCode':7}}}
            path.write_text(json.dumps(event)+'\n')
            row['outcome']={'passed':True};execution_observed(row)
            self.assertTrue(row['outcome']['passed'])

    def test_plan_mode_never_launches_paid_host(self):
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('run_v070_costs.py'))],
                              capture_output=True,text=True,encoding='utf-8',check=True)
        report=json.loads(result.stdout)
        self.assertEqual(report['paidCalls'],0)
        self.assertEqual(report['plannedAttempts'],72)
        self.assertEqual(len(FAMILY_MAPPING),12)
        self.assertEqual(FAMILY_MAPPING['multi-agent-cost-and-opportunity-attribution']['tasks'],[])

    def test_stop_file_finishes_current_pair_and_missing_file_does_not_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'stop'
            self.assertFalse(stop_at_pair_boundary(path,2))
            path.touch()
            self.assertTrue(stop_at_pair_boundary(path,0))
            self.assertFalse(stop_at_pair_boundary(path,1))
            self.assertTrue(stop_at_pair_boundary(path,2))
            self.assertFalse(stop_at_pair_boundary(None,2))

    def test_resume_retains_failed_rows_and_rejects_inflight_or_changed_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json'
            rows=[{'key':item['key'],'outcome':{'passed':False}} for item in schedule()[:2]]
            report={'interrupted':True,'complete':False,'activeAttempt':None,'reports':rows,
                    'model':'fixed','effort':'medium','configurations':{},'schedule':schedule(),
                    'evaluationSourceSha256':{},'acceptanceSha256':digest(ROOT/'verification/v070-acceptance-design.json')}
            path.write_text(json.dumps(report))
            resumed=resume_report(path,{},'fixed','medium')
            self.assertEqual(resumed['reports'],rows)
            self.assertFalse(resumed['interrupted'])
            with self.assertRaises(AssertionError):resume_report(path,{},'changed','medium')
            report['activeAttempt']='inflight';path.write_text(json.dumps(report))
            with self.assertRaises(AssertionError):resume_report(path,{},'fixed','medium')


if __name__=='__main__':
    unittest.main()
