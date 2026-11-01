"""Verify evidence remains actionable while native observations stay exact."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import workflow
import workflow_preview
import workflow_inline
from reducers import encode
from store import Store
from structured import analyze


class VerifyDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = self.temporary.name
        self.store = Store(self.root)

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def value(self, observation):
        return workflow.run(self.root, 'verify', {'results': [observation]}, 'review',
                            invoke=lambda *args: {'status': 'completed', 'items': []})

    def packet(self, value):
        receipt = workflow_preview.capture(self.store, value, 'verify')
        self.assertEqual(receipt['kind'], 'inline')
        return receipt['value']

    def visible(self, value):
        rendered = encode(value)
        return workflow_inline.eligible(rendered, analyze(rendered))

    def test_large_failure_direct_evidence_and_exact_source(self):
        native = {'exit_code': 2, 'output': 'INFO routine passed\n' * 800 + 'ERROR sentinel failure\n'}
        value = self.value(native)
        before = copy.deepcopy(value)
        packet = self.packet(value)
        self.assertEqual(packet['kind'], 'evidence-packet')
        self.assertEqual(packet['exitCode'], 2)
        self.assertEqual(packet['executionState'], 'completed')
        self.assertIn('sentinel failure', packet['diagnosis']['diagnostics'][-1]['text'])
        self.assertEqual(packet['diagnosis'], value['diagnosis'])
        self.assertEqual(packet['observationsRef']['path'], '/observations')
        self.assertEqual(self.store.get(packet['verificationRef']), value)
        self.assertEqual(value, before)
        self.assertTrue(self.visible(packet))
        self.assertLessEqual(len(encode(packet).encode()), workflow_preview.VERIFY_BYTES)
        parts, offset = [], 0
        while True:
            page = self.store.result(packet['verificationRef'], view='raw', path='/observations',
                                     offset=offset, max_bytes=5000)
            parts.append(page['text'])
            if page['nextOffset'] is None:
                break
            offset = page['nextOffset']
        self.assertEqual(json.loads(''.join(parts)), [native])

    def test_small_success_running_and_unknown_are_self_contained(self):
        for observation, state in [({'output': 'done', 'exit_code': 0}, 'completed'),
                                   ({'output': 'started', 'session_id': 42}, 'running'),
                                   ({'output': 'unknown native result'}, 'unknown')]:
            packet = self.packet(self.value(observation))
            self.assertEqual(packet['executionState'], state)
            self.assertEqual(packet['observations'], [observation])
            self.assertNotIn('observationsRef', packet)
            self.assertTrue(self.visible(packet))

    def test_excessive_observed_output_retains_skip_and_source(self):
        value = self.value({'exit_code': 1, 'output': 'x' * 262145})
        packet = self.packet(value)
        self.assertEqual(packet['exitCode'], 1)
        self.assertIsNone(packet['diagnosis'])
        self.assertIn('256 KiB', packet['diagnosticSkipped'])
        self.assertEqual(self.store.get(packet['verificationRef']), value)
        self.assertTrue(self.visible(packet))

    def test_large_diagnosis_context_omission_is_explicit(self):
        value = self.value({'exit_code': 1, 'output': 'ERROR failure'})
        value['diagnosis']['context'] = {'large': 'source context ' * 3000}
        packet = self.packet(value)
        self.assertEqual(packet['diagnosis']['diagnostics'], value['diagnosis']['diagnostics'])
        self.assertFalse(packet['coverage']['diagnosisComplete'])
        self.assertTrue(packet['coverage']['diagnosisContextOmitted'])
        self.assertEqual(packet['diagnosisRef']['path'], '/diagnosis')
        self.assertEqual(self.store.get(packet['verificationRef']), value)
        self.assertTrue(self.visible(packet))

    def test_large_diagnostics_prioritize_failure_and_report_omissions(self):
        value = self.value({'exit_code': 1, 'output': 'ERROR failure'})
        rows = [{'line': i + 1, 'text': 'INFO passed ' + 'x' * 1000} for i in range(39)]
        rows.append({'line': 40, 'text': 'ERROR important last line ' + 'z' * 1000})
        value['diagnosis']['diagnostics'] = rows
        before = copy.deepcopy(value)
        packet = self.packet(value)
        self.assertEqual(packet['diagnosis']['diagnostics'][0]['line'], 40)
        count = packet['coverage']['deliveryOmittedDiagnostics']
        self.assertGreater(count, 0)
        self.assertEqual(len(packet['diagnosis']['diagnostics']) + count, 40)
        self.assertEqual(value, before)
        self.assertLessEqual(len(encode(packet).encode()), workflow_preview.VERIFY_BYTES)
        self.assertTrue(self.visible(packet))

    def test_storage_failure_returns_original_unchanged(self):
        class Unavailable:
            def capture(self, *args, **kwargs):
                return {'status': 'error', 'error': {'code': 'CAPTURE_TOO_LARGE'}}
        value = self.value({'exit_code': 1, 'output': 'INFO passed\n' * 2000})
        result = workflow_preview.capture(Unavailable(), value, 'verify')
        self.assertIs(result['value'], value)

    def test_rejected_verification_stays_error(self):
        value = {'operation': 'verify', 'status': 'error', 'error': {'message': 'invalid arguments'}}
        self.assertEqual(self.packet(value), value)
        value = {'operation': 'other', 'status': 'completed'}
        self.assertEqual(self.packet(value), value)

    def test_unknown_states_references_and_diagnostics_not_whitelisted(self):
        base = self.packet(self.value({'exit_code': 1, 'output': 'ERROR failure'}))
        overrides = [
            {'executionState': 'completed', 'exitCode': True},
            {'executionState': 'running', 'exitCode': None, 'sessionId': None},
            {'executionState': 'wrong', 'exitCode': None},
            {'observations': []}, {'observations': ['not a native value']},
            {'diagnosis': []}, {'diagnosis': {'operation': 'other'}},
            {'diagnosis': {'operation': 'diagnose', 'diagnostics': [{'line': 0, 'text': 'wrong'}]}},
            {'observations': None, 'observationsRef': 'wrong'},
            {'observations': None, 'observationsRef': {'path': '/wrong'}},
            {'observations': None, 'observationsRef': {'path': '/observations'}, 'verificationRef': None},
            {'observations': None, 'observationsRef': {'path': '/observations'}, 'verificationRef': 'bad'},
            {'observations': None, 'observationsRef': {'path': '/observations', 'ref': 'ops://' + 'b' * 48},
             'verificationRef': 'ops://' + 'a' * 48},
        ]
        for update in overrides:
            self.assertFalse(self.visible({**base, **update}), update)

    def test_error_content_does_not_gain_generic_packet_exemption(self):
        packet = self.packet(self.value({'exit_code': 1, 'output': 'ERROR failure'}))
        packet['diagnosis']['error'] = {'message': 'native error must retain existing error handling'}
        self.assertFalse(self.visible(packet))


if __name__ == '__main__':
    unittest.main()
