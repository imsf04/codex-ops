import json
import unittest

import capability_catalog
import workflow_diagnostics


class AdoptionRepairs(unittest.TestCase):
    def test_late_failures_displace_success_noise_and_keep_original_line_numbers(self):
        lines = [f'INFO asset={i} status=passed' for i in range(90)]
        lines += ['WARN fallback=local', 'ERROR code=INVALID_REGION',
                  'ERROR code=VALIDATION_ABORTED', 'ERROR code=BUILD_FAILED']
        evidence, omitted = workflow_diagnostics._evidence(lines, 12)
        self.assertEqual(len(evidence), 12)
        self.assertEqual(omitted, 82)
        self.assertEqual([item['line'] for item in evidence[-4:]], [91, 92, 93, 94])
        self.assertEqual([item['text'] for item in evidence[-4:]], lines[-4:])

    def test_tight_budget_selects_failure_before_warning_and_success(self):
        lines = ['1 passed', 'WARNING fallback', 'AssertionError: failed', 'ERROR caused_by=bad']
        evidence, omitted = workflow_diagnostics._evidence(lines, 2)
        self.assertEqual([item['line'] for item in evidence], [3, 4])
        self.assertEqual(omitted, 2)
        self.assertEqual(workflow_diagnostics._evidence(['ordinary line'], 12), ([], 0))

    def test_priority_uses_full_line_before_display_clipping(self):
        evidence, _ = workflow_diagnostics._evidence(['passed', 'x' * 900 + ' ERROR failed'], 1)
        self.assertEqual(evidence[0]['line'], 2)
        self.assertTrue(evidence[0]['clipped'])
        self.assertEqual(len(evidence[0]['text']), 800)

    def test_catalogue_leads_with_direct_calls_and_defers_sdk_source(self):
        result = capability_catalog.workflows()
        self.assertNotIn('javascript', result)
        self.assertNotIn('typescript', result)
        self.assertEqual({row['operation'] for row in result['recipes']},
                         {'locate', 'diagnose', 'documents', 'incremental', 'investigate', 'evidence', 'working_set', 'verify'})
        self.assertEqual(result['sdk']['operation'], 'sdk')
        self.assertLess(len(json.dumps(result, indent=2).encode()), 4800)


if __name__ == '__main__':
    unittest.main()
