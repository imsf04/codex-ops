"""A native handshake is not an acknowledgement of the later projected output."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bridge_probe_status


class BridgeProbeStatusTests(unittest.TestCase):
    def test_projection_waits_for_the_next_heartbeat_after_handshake(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            initial = {'counters': {'outboundFrames': 4, 'compactedFrames': 0}}
            finished = {'counters': {'outboundFrames': 8, 'compactedFrames': 2}}
            path.write_text(json.dumps(initial), encoding='utf-8')
            with patch.object(bridge_probe_status.time, 'sleep', side_effect=lambda _: path.write_text(
                    json.dumps(finished), encoding='utf-8')):
                result = bridge_probe_status.wait_for_status(path, projected=True)
            self.assertEqual(result, finished)

    def test_missing_projection_fails_without_reexecuting_the_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            path.write_text(json.dumps({'counters': {'outboundFrames': 4, 'compactedFrames': 0}}))
            with patch.object(bridge_probe_status.time, 'monotonic', side_effect=[0, 0, 5]), \
                    patch.object(bridge_probe_status.time, 'sleep'), self.assertRaisesRegex(
                        AssertionError, 'did not publish'):
                bridge_probe_status.wait_for_status(path, projected=True)
