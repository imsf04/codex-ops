"""Structural evidence is grounded in retained native payloads, not success labels."""
import copy
import json
from pathlib import Path
import unittest

import task_cost_workflows as workflows


class WorkingSetEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(__file__).parent/'fixtures/v080-working-set-native.json'
        cls.rows = json.loads(fixture.read_text(encoding='utf-8'))['rows']

    def test_native_current_and_partial_payloads_contain_structural_evidence(self):
        for row in self.rows:
            with self.subTest(eventLine=row['eventLine']):
                result = workflows.assess(row['value'])
                self.assertEqual(result['evidence'],'present')
                self.assertEqual(result['outcome'],row['value']['status'])
                self.assertFalse(result['reused'])

    def test_empty_unavailable_omitted_and_stale_old_only_remain_unknown(self):
        value = copy.deepcopy(self.rows[0]['value'])
        item = value['items'][0]
        value['items'] = [item]
        for state in ('unavailable','omitted','stale'):
            item['state'] = state
            self.assertEqual(workflows.assess(value)['evidence'],'unknown')
        item['state'] = 'current'
        item['result']['items'] = []
        self.assertEqual(workflows.assess(value)['evidence'],'unknown')
        item['result']['items'] = [{'text':'   '}]
        self.assertEqual(workflows.assess(value)['evidence'],'unknown')
        value['items'] = []
        self.assertEqual(workflows.assess(value)['evidence'],'unknown')

    def test_saved_observation_requires_actual_rows(self):
        value = copy.deepcopy(self.rows[0]['value'])
        value['items'] = [value['items'][0]]
        item = value['items'][0]
        item['state'] = 'saved-observation'
        self.assertEqual(workflows.assess(value)['evidence'],'present')
        item['result'] = {'kind':'reference','ref':item['ref']}
        self.assertEqual(workflows.assess(value)['evidence'],'unknown')

    def test_stale_payload_needs_matching_new_revision_and_nonempty_native_rows(self):
        value = copy.deepcopy(self.rows[1]['value'])
        item = next(item for item in value['items'] if item['state']=='stale')
        value['items'] = [item]
        item['currentEvidence'] = {'path':item['path'],'revision':item['currentRevision'],
                                   'items':[{'line':1,'text':'{"workers":7}'}],'complete':True}
        self.assertEqual(workflows.assess(value)['evidence'],'present')
        item['currentEvidenceOmitted'] = True
        self.assertEqual(workflows.assess(value)['evidence'],'unknown')
        del item['currentEvidenceOmitted']
        for revision in (None,'',item['revision'],'mismatched-new-revision'):
            item['currentEvidence']['revision'] = revision
            self.assertEqual(workflows.assess(value)['evidence'],'unknown')
        item['currentEvidence']['revision'] = item['currentRevision']
        item['currentEvidence']['items'] = []
        self.assertEqual(workflows.assess(value)['evidence'],'unknown')


if __name__ == '__main__':
    unittest.main()
