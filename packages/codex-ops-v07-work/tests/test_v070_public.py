"""Exercise the complete public workflow/store/presentation connection."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import server
import adaptive_budget_ledger
from presentation_policy import Presenter
from store import Store

A = '01a18391-1809-7601-96cc-09b2c96329c1'
B = '01a18391-1809-7601-96cc-09b2c96329c2'


def ctx(identity=A):
    return SimpleNamespace(request_context=SimpleNamespace(meta={'threadId': identity}))


def value(result):
    return result['value'] if result.get('kind') == 'inline' else result


class PublicEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = patch.dict(os.environ, {'CODEX_OPS_STORE': str(self.root / 'cache'),
            'CODEX_OPS_MEASUREMENT_ORIGIN': 'validation'})
        environment.start()
        self.addCleanup(environment.stop)

    def call(self, operation, args, identity=A):
        return value(server.ops_workflow(str(self.root), operation, args, ctx(identity)))

    def saved(self, text):
        return server.ops_capture(text * 800, ctx())['ref']

    def test_investigation_is_inline_and_program_value_stays_complete(self):
        (self.root / 'limit.py').write_text('RETRY_LIMIT = 17\ndef cap(n):\n    return min(n, RETRY_LIMIT)\n')
        result = self.call('investigate', {'question': 'Where is RETRY_LIMIT used?'})
        self.assertEqual(result['evidenceState'], 'collected')
        self.assertIn('return min', json.dumps(result))
        emitted = json.dumps(result)
        self.assertEqual(Presenter().render(emitted), emitted)
        self.assertEqual(json.dumps(result), emitted)
        self.assertEqual(self.call('investigate', {'question': '为什么这里这样做'})['evidenceState'], 'needs_anchor')
        self.assertEqual(self.call('investigate', {'question': 'cap', 'maxBytes': 16000})['operation'], 'investigate')

    def test_reference_search_and_recovery_do_not_add_recapture_or_authority(self):
        ref = self.saved('failure at alpha\n')
        found = self.call('evidence', {'refs': [ref], 'query': 'alpha'})
        self.assertEqual(found['kind'], 'evidence-packet')
        self.assertIn('alpha', found['items'][0]['text'])
        encoded = json.dumps(found)
        self.assertEqual(Presenter().render(encoded), encoded)
        denied = self.call('evidence', {'refs': [ref], 'query': 'alpha'}, B)
        self.assertEqual(denied['evidenceState'], 'unavailable')
        self.assertEqual(denied['items'], [])
        receipt = self.call('working_set', {'action': 'save', 'sources': [{'ref': ref}], 'pending': ['check final tests']})
        resumed = self.call('working_set', {'action': 'resume', 'workingSetRef': receipt['workingSetRef'], 'maxBytes': 24000})
        self.assertEqual(resumed['kind'], 'evidence-packet')
        self.assertEqual(resumed['items'][0]['state'], 'saved-observation')
        self.assertEqual(Presenter().render(json.dumps(resumed)), json.dumps(resumed))
        server.ops_result(ref, action='release', ctx=ctx())
        gone = self.call('working_set', {'action': 'resume', 'workingSetRef': receipt['workingSetRef']})
        self.assertEqual(gone['items'][0]['state'], 'unavailable')

    def test_repeated_immediate_reads_connect_to_investigation_budget(self):
        refs = [self.saved(f'long observation {i}\n') for i in range(4)]
        for ref in refs[:2]:
            server.ops_result(ref, view='raw', ctx=ctx())
        policy = adaptive_budget_ledger.budget('chat:' + A)
        self.assertEqual(policy['recommendedBytes'], 16384)
        with patch.object(server.workflow, 'run', return_value={'status': 'completed'}) as run:
            self.call('investigate', {'question': 'cap'})
            self.assertEqual(run.call_args.args[2]['maxBytes'], 16384)
            self.call('investigate', {'question': 'cap', 'maxBytes': 4096})
            self.assertEqual(run.call_args.args[2]['maxBytes'], 4096)
        self.assertEqual(adaptive_budget_ledger.budget('chat:' + B)['recommendedBytes'], 12288)

    def test_stats_never_guess_a_chat_and_sdk_is_available_in_one_call(self):
        stats = server.ops_stats()
        self.assertFalse(stats['taskCosts']['available'])
        sdk = self.call('sdk', {})
        self.assertEqual(sdk['operation'], 'sdk')
        self.assertIn('verifyRun', sdk['javascript'])
        self.assertEqual(self.call('evidence', {'refs': [], 'query': 'x'})['status'], 'error')

    def test_native_verify_analyzes_failure_without_execution(self):
        result = self.call('verify', {'results': [{'exit_code': 2, 'output': 'ERROR deliberate failure'}]})
        self.assertIn('deliberate failure', json.dumps(result))
        self.assertEqual(list(self.root.glob('*.py')), [])


if __name__ == '__main__':
    unittest.main()
