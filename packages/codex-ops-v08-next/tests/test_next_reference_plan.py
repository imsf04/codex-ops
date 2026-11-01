import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import prepare_next_reference_plan as plan


class ReferencePlanTests(unittest.TestCase):
    def test_failed_reference_rows_are_retained_and_missing_measurements_rejected(self):
        row = {'key':'1-task-v070','condition':'v070','task':'task','repeat':1,
               'outcome':{'passed':False},'eligibleForComparison':True}
        report = {'complete':True,'reports':[row]}
        refs = plan.reference_rows(report,{'sha256':'bound'}, {'v070':1})
        self.assertFalse(refs[0]['originalStrictPassed'])
        row['eligibleForComparison'] = False
        with self.assertRaises(AssertionError):
            plan.reference_rows(report,{'sha256':'bound'}, {'v070':1})

    def test_real_schedules_keep_all_repeats_and_terminal_protocol_separate(self):
        original = plan.read(plan.OLD/'verification/v080-full-1.json')['schedule']
        saved = copy.deepcopy(original)
        self.assertEqual(len(plan.candidate_schedule(original)),48)
        screen = plan.candidate_schedule(original,screen=True)
        self.assertEqual(len(screen),12)
        self.assertEqual({r['task'] for r in screen},set(plan.SCREEN_TASKS))
        terminal = plan.candidate_schedule(original,supplemental=True)
        self.assertEqual({r['repeat'] for r in terminal},{1,2,3})
        self.assertEqual(original,saved)

    def test_changed_artifact_bytes_fail_the_reference_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'source.py').write_bytes(b'old bytes')
            expected = {'source.py':hashlib.sha256(b'old bytes').hexdigest()}
            plan.verify_files(root,expected)
            (root/'source.py').write_bytes(b'new bytes')
            with self.assertRaises(AssertionError):
                plan.verify_files(root,expected)


if __name__=='__main__':
    unittest.main()
