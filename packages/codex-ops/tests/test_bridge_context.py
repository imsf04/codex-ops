from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge_context import SERVICE, context, mcp_context
from runtime_bridge.wire import pack_varint

A = 'cf47464f-0f6b-466b-902b-11ecf5bb3769'
B = '0be65cdf-5748-4dfe-a88e-448807e0f7a5'
THREAD = '01a18391-1809-7601-96cc-09b2c96329c1'


def field(n, value):
    raw = value.encode() if isinstance(value, str) else value
    return pack_varint((n << 3) | 2) + pack_varint(len(raw)) + raw


class BridgeContextTests(unittest.TestCase):
    def test_native_session_is_stable_across_invocations_and_wait(self):
        first = context(SERVICE + 'Execute', field(1, A) + field(2, B) + field(3, 'call_1'))
        second = context(SERVICE + 'Execute', field(1, A) + field(2, THREAD) + field(3, 'call_2'))
        wait = context(SERVICE + 'Wait', field(1, A) + field(2, '1') + field(3, B))
        self.assertEqual(first, second)
        self.assertEqual(first, {'tool': 'functions.exec', 'session': 'code-mode:' + A, 'sessionKind': 'code-mode'})
        self.assertEqual(wait['session'], first['session'])
        self.assertEqual(wait['tool'], 'functions.wait')
        self.assertNotEqual(context(SERVICE + 'Execute', field(1, B))['session'], first['session'])

    def test_unknown_malformed_and_notification_requests_never_invent_session(self):
        self.assertEqual(context(SERVICE + 'NewMethod', field(1, A)), {})
        self.assertEqual(context(SERVICE + 'OpenSession', field(1, A)), {'tool': 'code_mode.notify'})
        bad = [b'', b'\x80', b'\x08\x01', field(1, b'\xff'), field(1, 'anything'),
               field(1, A) + field(1, A), None]
        for raw in bad:
            self.assertEqual(context(SERVICE + 'Execute', raw), {'tool': 'functions.exec'})
        with patch('bridge_context.MAX_REQUEST_BYTES', 1):
            self.assertEqual(context(SERVICE + 'Wait', field(1, A)), {'tool': 'functions.wait'})

    def test_mcp_thread_and_window_are_request_metadata_not_grpc_ids(self):
        meta = {'threadId': THREAD, 'windowId': THREAD + ':0',
                'x-codex-turn-metadata': {'thread_id': THREAD, 'sandbox_mode': 'read-only'}}
        result = mcp_context(meta, 'ops_files')
        self.assertEqual(result, {'tool': 'ops_files', 'session': 'chat:' + THREAD,
                                 'sessionKind': 'chat', 'window': THREAD + ':0'})
        self.assertNotIn('sandbox_mode', result)
        self.assertEqual(mcp_context({'threadId': THREAD}, 'ops_result')['session'], 'chat:' + THREAD)

    def test_absent_conflicting_and_invalid_metadata_stays_unattributed(self):
        cases = [None, [], {}, {'threadId': 1}, {'threadId': 'spoof'},
                 {'threadId': THREAD, 'x-codex-turn-metadata': []},
                 {'threadId': THREAD, 'x-codex-turn-metadata': {'thread_id': A}}]
        for meta in cases:
            self.assertEqual(mcp_context(meta, 'ops_files'), {'tool': 'ops_files'})
        for window in [None, 1, A + ':0', THREAD + ':', THREAD + ':wrong',
                       THREAD + ':١', THREAD + ':' + '1' * 13]:
            result = mcp_context({'threadId': THREAD, 'windowId': window}, 'ops_files')
            self.assertEqual(result, {'tool': 'ops_files', 'session': 'chat:' + THREAD, 'sessionKind': 'chat'})


if __name__ == '__main__':
    unittest.main()
