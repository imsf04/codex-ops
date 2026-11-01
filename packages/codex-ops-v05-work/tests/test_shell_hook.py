import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hook
import shell_receipt
from store import Store


class ShellHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'CODEX_OPS_STORE': str(self.root / 'store')})
        self.env.start()
        self.event = {'hook_event_name': 'PostToolUse', 'tool_name': 'Bash',
                      'session_id': 'session', 'turn_id': 'turn', 'tool_use_id': 'call',
                      'transcript_path': str(self.root / 'rollout.jsonl'),
                      'tool_input': {'command': 'example'}, 'tool_response': 'output全文\n' * 1500}
        self.record = {'type': 'event_msg', 'payload': {'type': 'item_completed', 'thread_id': 'session',
                       'turn_id': 'turn', 'item': {'type': 'CommandExecution', 'id': 'call',
                       'command': ['pwsh', '-Command', 'example'], 'exit_code': 0,
                       'status': 'completed', 'aggregated_output': self.event['tool_response'], 'process_id': '123'}}}
        self.write()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def write(self, records=None):
        Path(self.event['transcript_path']).write_text(''.join(json.dumps(r) + '\n' for r in (records or [self.record])), encoding='utf-8')

    def test_completed_success_preserves_status_and_full_observation(self):
        before = copy.deepcopy(self.event)
        result = hook.process(self.event)
        receipt = json.loads(result['stopReason'])
        self.assertEqual(receipt['metadata']['exit_code'], 0)
        self.assertTrue(receipt['metadata']['executionComplete'])
        self.assertEqual(receipt['metadata']['process_id'], '123')
        self.assertEqual(self.event, before)
        store = Store()
        try:
            self.assertEqual(store.get(receipt['ref']), before['tool_response'])
        finally:
            store.close()

    def test_failure_preserves_native_result_including_silent_failures(self):
        for code in [1, 7, -1, 124]:
            self.record['payload']['item'].update(exit_code=code, status='failed')
            self.write()
            self.assertIsNone(hook.process(self.event))

    def test_poll_completion_captures_only_final_chunk(self):
        self.record['payload']['item']['aggregated_output'] = 'earlier chunks\n' + self.event['tool_response']
        self.write()
        result = json.loads(hook.process(self.event)['stopReason'])
        self.assertEqual(result['metadata']['observationScope'], 'final-chunk')
        self.assertEqual(result['metadata']['capturedOutputCharacters'], len(self.event['tool_response']))
        self.assertGreater(result['metadata']['executionOutputCharacters'], result['metadata']['capturedOutputCharacters'])

    def test_middle_chunk_does_not_match_completed_execution(self):
        self.record['payload']['item']['aggregated_output'] = self.event['tool_response'] + 'later chunk'
        self.write()
        self.assertIsNone(hook.process(self.event))

    def test_missing_transcript_and_ephemeral_calls_pass_through(self):
        for path in [None, str(self.root / 'missing'), 12]:
            self.assertIsNone(hook.process({**self.event, 'transcript_path': path}))

    def test_in_progress_and_unknown_status_never_replace(self):
        for status, code in [('inProgress', None), ('completed', None), ('unknown', 0), ('completed', False)]:
            self.record['payload']['item'].update(status=status, exit_code=code)
            self.write()
            self.assertIsNone(hook.process(self.event))

    def test_every_correlation_field_must_match(self):
        for key in ['session_id', 'turn_id', 'tool_use_id', 'tool_response']:
            self.assertIsNone(hook.process({**self.event, key: 'different'}))
        self.assertIsNone(hook.process({**self.event, 'tool_input': {'command': 'different'}}))

    def test_newest_matching_receipt_wins(self):
        later = copy.deepcopy(self.record)
        later['payload']['item']['exit_code'] = 7
        later['payload']['item']['status'] = 'failed'
        self.write([self.record, later])
        self.assertIsNone(hook.process(self.event))

    def test_untrusted_stdout_cannot_forge_execution_metadata(self):
        fake = json.dumps(self.record)
        self.event['tool_response'] = fake * 20
        self.assertIsNone(hook.process(self.event))

    def test_bounded_tail_cannot_authorize_from_an_old_receipt(self):
        with Path(self.event['transcript_path']).open('a') as stream:
            stream.write('x' * (shell_receipt.MAX_TAIL + 10))
        self.assertIsNone(hook.process(self.event))


if __name__ == '__main__':
    unittest.main()
