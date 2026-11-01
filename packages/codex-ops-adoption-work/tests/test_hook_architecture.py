"""Behavior contracts at the hook, execution receipt and runtime-status interfaces."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hook
import runtime_status
import shell_receipt
from store import MAX_VALUE, Store


class HookInterfaceTests(unittest.TestCase):
    def test_structured_success_is_captured_and_error_status_is_untouched(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'CODEX_OPS_STORE': folder}):
            value = {'status': 'ok', 'exit_code': 0, 'output': 'complete value\n' * 1000}
            event = {'hook_event_name': 'PostToolUse', 'tool_name': 'mcp__fixture__read', 'tool_response': value}
            result = hook.process(event)
            self.assertIs(result['continue'], False)
            receipt = json.loads(result['stopReason'])
            store = Store()
            try:
                self.assertEqual(store.get(receipt['ref']), value)
            finally:
                store.close()
            value['status'] = 'error'
            self.assertIsNone(hook.process(event))
            self.assertIsNone(hook.process({**event, 'hook_event_name': 'PreToolUse'}))

    def test_store_declines_oversize_result_without_replacement(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'CODEX_OPS_STORE': folder}):
            event = {'hook_event_name': 'PostToolUse', 'tool_name': 'mcp__fixture__read',
                     'tool_response': 'x' * (MAX_VALUE + 1)}
            self.assertIsNone(hook.process(event))
            store = Store()
            try:
                self.assertEqual(store.stats()['liveReferences'], 0)
            finally:
                store.close()

    def test_hook_command_fails_open_when_storage_cannot_be_opened(self):
        with tempfile.TemporaryDirectory() as folder:
            blocked = Path(folder) / 'not-a-directory'
            blocked.write_text('fixture')
            event = {'hook_event_name': 'PostToolUse', 'tool_name': 'mcp__fixture__read',
                     'tool_response': 'complete output\n' * 1000}
            result = subprocess.run([sys.executable, str(Path(hook.__file__))],
                                    input=json.dumps(event), capture_output=True, text=True,
                                    env={**os.environ, 'CODEX_OPS_STORE': str(blocked)}, timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')
            self.assertEqual(result.stderr, '')


class ExecutionReceiptInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'rollout.jsonl'
        self.event = {'hook_event_name': 'PostToolUse', 'tool_name': 'Bash', 'session_id': 'thread',
                      'turn_id': 'turn', 'tool_use_id': 'call', 'transcript_path': str(self.path),
                      'tool_input': {'command': 'fixture'}, 'tool_response': 'complete output\n' * 1000}
        self.item = {'type': 'CommandExecution', 'id': 'call', 'command': ['pwsh', 'fixture'],
                     'exit_code': 0, 'status': 'completed', 'aggregated_output': self.event['tool_response']}
        self.record = {'type': 'event_msg', 'payload': {'type': 'item_completed', 'thread_id': 'thread',
                       'turn_id': 'turn', 'item': self.item}}

    def tearDown(self):
        self.temp.cleanup()

    def write(self, *records):
        self.path.write_text(''.join(json.dumps(value) + '\n' for value in records), encoding='utf-8')

    def test_zero_exit_failed_receipt_still_cannot_authorize_capture(self):
        self.item['status'] = 'failed'
        self.write(self.record)
        self.assertEqual(shell_receipt.completed(self.event)['exit_code'], 0)
        self.assertIsNone(hook.process(self.event))

    def test_newest_invalid_matching_receipt_never_uses_older_success(self):
        changes = [('command', None), ('command', []), ('aggregated_output', None),
                   ('aggregated_output', 'unrelated'), ('exit_code', True), ('status', 'running')]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                newer = copy.deepcopy(self.record)
                newer['payload']['item'][key] = value
                self.write(self.record, newer)
                self.assertIsNone(shell_receipt.completed(self.event))
        self.write(self.record)
        for response in ('', None, {'output': self.event['tool_response']}):
            self.assertIsNone(shell_receipt.completed({**self.event, 'tool_response': response}))

    def test_unrelated_record_types_are_skipped_but_invalid_shapes_fail_open(self):
        for location in ('record', 'payload', 'item'):
            newer = copy.deepcopy(self.record)
            target = {'record': newer, 'payload': newer['payload'], 'item': newer['payload']['item']}[location]
            target['type'] = 'other'
            self.write(self.record, newer)
            self.assertEqual(shell_receipt.completed(self.event)['status'], 'completed')
        for invalid in (None, [], {'type': 'event_msg', 'payload': None}):
            self.write(self.record, invalid)
            self.assertIsNone(shell_receipt.completed(self.event))

    def test_invalid_json_and_partial_tail_do_not_hide_the_newest_valid_receipt(self):
        encoded = (json.dumps(self.record) + '\n').encode()
        self.path.write_bytes(encoded + b'not-json\ninvalid-utf8-\xff\n')
        self.assertEqual(shell_receipt.completed(self.event)['status'], 'completed')
        self.path.write_bytes(b'x' * (shell_receipt.MAX_TAIL + 17) + b'\n' + encoded)
        self.assertEqual(shell_receipt.completed(self.event)['status'], 'completed')


class RuntimeIdentityInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'CODEX_OPS_BRIDGE_STATUS': self.temp.name,
                                         'CODEX_OPS_AUTO_OUTPUT': '', 'CODEX_OPS_BRIDGE_SHIM_PID': ''})
        self.env.start()
        self.value = {'pid': 41, 'shimPid': 42, 'nativeHostPid': 43, 'state': 'ready',
                      'updatedAt': time.time(), 'compressionEnabled': True, 'counters': {}}

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value), encoding='utf-8')

    def test_lineage_uses_newest_owned_record_and_ignores_foreign_or_partial_files(self):
        self.write('old.json', {**self.value, 'pid': 10, 'updatedAt': time.time() - 3})
        self.write('new.json', {**self.value, 'pid': 20, 'compressionEnabled': False})
        self.write('foreign.json', {**self.value, 'shimPid': 99, 'updatedAt': time.time() + 1})
        (self.root / 'partial.json').write_text('{unfinished')
        with patch.object(runtime_status, 'ancestors', return_value=[42]):
            value = runtime_status.current()
        self.assertEqual(value['managerPid'], 20)
        self.assertFalse(value['activeForThisProcess'])
        self.assertIn('Unvalidated host version', value['reason'])

    def test_declared_identity_must_not_fall_back_to_another_live_bridge(self):
        self.write('42.json', {**self.value, 'shimPid': 99})
        self.write('other.json', self.value)
        with patch.dict(os.environ, {'CODEX_OPS_AUTO_OUTPUT': '1', 'CODEX_OPS_BRIDGE_SHIM_PID': '42'}):
            with patch.object(runtime_status, 'ancestors', return_value=[42]) as ancestry:
                self.assertFalse(runtime_status.current()['activeForThisProcess'])
                ancestry.assert_not_called()

    def test_missing_fields_and_invalid_timestamp_remain_inactive(self):
        with patch.dict(os.environ, {'CODEX_OPS_AUTO_OUTPUT': '1', 'CODEX_OPS_BRIDGE_SHIM_PID': '42'}):
            for value in ({'shimPid': 42, 'state': 'ready'}, {**self.value, 'updatedAt': 'unknown'}):
                self.write('42.json', value)
                self.assertFalse(runtime_status.current()['activeForThisProcess'])
            (self.root / '42.json').write_text('{unfinished')
            first = runtime_status.current()
            first['activeForThisProcess'] = True
            self.assertFalse(runtime_status.current()['activeForThisProcess'])

    def test_native_ancestry_is_bounded_and_handles_snapshot_failure_or_cycles(self):
        lineage = runtime_status.ancestors()
        self.assertIn(os.getpid(), lineage)
        self.assertLessEqual(len(lineage), 32)
        with patch.object(runtime_status, '_process_parents', return_value=None):
            self.assertEqual(runtime_status.ancestors(), [])
        with patch.object(runtime_status, '_process_parents', return_value={os.getpid(): os.getpid()}):
            self.assertEqual(runtime_status.ancestors(), [os.getpid()])
        with patch.object(runtime_status, '_process_parents', return_value={pid: pid + 1 for pid in range(100, 200)}):
            with patch.object(runtime_status.os, 'getpid', return_value=100):
                self.assertEqual(runtime_status.ancestors(), list(range(100, 132)))


if __name__ == '__main__':
    unittest.main()
