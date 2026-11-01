import copy
import json
import unittest
from unittest.mock import patch

import hook
import workflow_view
from presentation_policy import Presenter
import test_v080_delivery


class RecoveryViewTests(unittest.TestCase):
    def current(self):
        return {'path': 'settings.json', 'revision': 'new', 'status': 'partial',
                'items': [{'path': 'settings.json', 'line': 17, 'text': '{"workers":7}'}],
                'complete': False, 'truncated': True, 'nextOffset': 81,
                'requestedWindow': {'offset': 17, 'limit': 64},
                'coverageMeaning': 'Fresh native read window; saved lines outside this window are not refreshed.'}

    def item(self):
        return {'kind': 'working-source', 'state': 'stale',
                'source': {'path': 'settings.json', 'revision': 'old'},
                'ref': 'ops://old', 'currentRevision': 'new',
                'result': '{"workers":3}', 'currentEvidence': self.current()}

    def show(self, item):
        value = {'operation': 'working_set', 'status': 'completed', 'items': [item]}
        original = copy.deepcopy(value)
        shown = workflow_view.project(value)
        self.assertEqual(value, original)
        return shown

    def test_saved_availability_is_explicit_without_requiring_resume(self):
        for state in ('saved', 'unavailable', 'unattributed-or-empty'):
            value = {'operation': 'investigate', 'items': [], 'workingSet': {'state': state}}
            shown = workflow_view.project(value)
            if state == 'saved':
                self.assertEqual(shown['workingSet'], {'state': 'saved', 'availableForLater': True})
            else:
                self.assertNotIn('workingSet', shown)

    def test_stale_source_and_fresh_window_have_separate_revision_and_coverage(self):
        shown = self.show(self.item())
        self.assertEqual(shown['sources'], [{'path': 'settings.json', 'revision': 'old'},
                                            {'path': 'settings.json', 'revision': 'new'}])
        old, fresh = shown['evidence']
        self.assertEqual(old['state'], 'stale')
        self.assertNotIn('text', old)
        self.assertEqual(fresh, {'source': 2, 'state': 'current-read', 'line': 17, 'text': '{"workers":7}'})
        self.assertEqual(shown['currentReads'][0]['requestedWindow'], {'offset': 17, 'limit': 64})
        self.assertFalse(shown['currentReads'][0]['complete'])
        self.assertEqual(shown['currentReads'][0]['nextOffset'], 81)
        self.assertEqual(shown['omittedDisplayRows'], 0)

    def test_invalid_or_unverified_current_payload_never_becomes_current_evidence(self):
        invalid = [None, {}, {'status': 'failed'}, {**self.current(), 'revision': 'other'},
                   {**self.current(), 'path': ''}, {**self.current(), 'items': None}]
        for current in invalid:
            with self.subTest(current=current):
                item = {**self.item(), 'currentEvidence': current}
                shown = self.show(item)
                self.assertEqual(len(shown['evidence']), 1)
                self.assertNotIn('currentReads', shown)

    def test_omitted_fresh_evidence_has_its_own_reference_not_old_snapshot(self):
        item = {**self.item(), 'currentEvidenceOmitted': True,
                'currentRead': {key: self.current()[key] for key in ('path', 'revision', 'requestedWindow')},
                'currentEvidenceRef': 'ops://fresh'}
        shown = self.show(item)
        self.assertEqual(shown['evidence'][1], {'source': 2, 'state': 'current-read',
                                               'contentOmitted': True, 'ref': 'ops://fresh'})
        self.assertEqual(shown['sources'][1]['revision'], 'new')
        del item['currentEvidenceRef']
        self.assertNotIn('ref', self.show(item)['evidence'][1])
        for descriptor in (None, {}, {'path': 'settings.json', 'revision': 'wrong'}):
            item['currentRead'] = descriptor
            self.assertEqual(len(self.show(item)['evidence']), 1)

    def test_fresh_rows_keep_clipping_and_ignore_non_line_payloads(self):
        item = self.item()
        item['currentEvidence']['items'] += [None, {}, {'line': True, 'text': 'wrong'}, {'line': 8, 'text': None}]
        item['currentEvidence']['items'][0]['truncatedInLine'] = True
        shown = self.show(item)
        self.assertEqual(len(shown['evidence']), 2)
        self.assertTrue(shown['evidence'][1]['clipped'])
        item['state'] = 'unavailable'
        self.assertEqual(len(self.show(item)['evidence']), 1)

    def test_active_guidance_has_one_call_entry_and_later_recovery_semantics(self):
        with patch('hook.runtime_status.current', return_value={'activeForThisProcess': True}):
            guidance = hook._session_start()['hookSpecificOutput']['additionalContext']
        self.assertIn('tools.mcp__codex_ops__ops_workflow', guidance)
        self.assertNotIn('ALL_TOOLS', guidance)
        self.assertIn('Use delivered evidence to finish', guidance)
        self.assertIn('available for later', guidance)
        self.assertIn('current-read', guidance)


class RecoveryRawTests(unittest.TestCase):
    setUp = test_v080_delivery.DeliveryTests.setUp
    packet = test_v080_delivery.DeliveryTests.packet
    raw = test_v080_delivery.DeliveryTests.raw

    def test_new_recovery_view_retains_exact_original_and_machine_value(self):
        value = self.packet()
        value['workingSet'] = {'state': 'saved', 'workingSetRef': 'ops://saved'}
        original = copy.deepcopy(value)
        raw = json.dumps({'content': [{'type': 'text', 'text': json.dumps({'kind': 'inline', 'value': value})}]})
        shown = json.loads(Presenter().render(raw))
        self.assertEqual(shown['workingSet'], {'state': 'saved', 'availableForLater': True})
        self.assertEqual(self.raw(shown['ref']), raw)
        self.assertEqual(value, original)


if __name__ == '__main__':
    unittest.main()
