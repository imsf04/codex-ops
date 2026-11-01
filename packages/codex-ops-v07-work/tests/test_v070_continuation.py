import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from run_v070_continuation import continuation_plan
from run_v070_costs import schedule
from v070_fixture_continuation import prepare_task, REVISION
import v070_model_tasks


class ContinuationTests(unittest.TestCase):
    def test_adapter_changes_only_producer_and_its_protected_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=v070_model_tasks.prepare_task('long_command_failure',root/'old')
            revised=prepare_task('long_command_failure',root/'new')
            self.assertEqual(old['answer'],revised['answer'])
            self.assertEqual(old['requiredFiles'],revised['requiredFiles'])
            self.assertEqual(old['spec'],revised['spec'])
            self.assertIn(b'.write_bytes(b"completed-with-exit-7\\n")',(root/'new/run_probe.py').read_bytes())
            self.assertEqual(hashlib.sha256((root/'new/run_probe.py').read_bytes()).hexdigest(),revised['preserved']['run_probe.py'])
            self.assertNotEqual(old['preserved']['run_probe.py'],revised['preserved']['run_probe.py'])

    def test_28_original_rows_retain_26_and_run_46_without_changing_original_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json'
            rows=[{**item,'outcome':{'passed':False},'tokens':{'total':{'inputTokens':12}}} for item in schedule()[:28]]
            source={'interrupted':True,'complete':False,'activeAttempt':None,'reports':rows,'schedule':schedule()}
            path.write_text(json.dumps(source));before=path.read_bytes()
            plan=continuation_plan(source,path)
            self.assertEqual(len(plan['retained']),26);self.assertEqual(len(plan['pending']),46)
            self.assertEqual(len(plan['excludedInvalidFixtureAttempts']),2)
            self.assertTrue(all(not r['outcome']['passed'] for r in plan['excludedInvalidFixtureAttempts']))
            self.assertEqual(len([i for i in plan['pending'] if i['task']=='long_command_failure']),6)
            self.assertTrue(all(i['key'].endswith(REVISION) for i in plan['pending'] if i['task']=='long_command_failure'))
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(source['reports'],rows)

    def test_inflight_source_cannot_be_retried_implicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json';path.write_text('{}')
            with self.assertRaises(AssertionError):
                continuation_plan({'interrupted':True,'complete':False,'activeAttempt':'paid-inflight','reports':[]},path)


if __name__=='__main__':unittest.main()
