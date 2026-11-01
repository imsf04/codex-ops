import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hook
import runtime_status


class RuntimeStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'CODEX_OPS_AUTO_OUTPUT': '1', 'CODEX_OPS_BRIDGE_SHIM_PID': '42', 'CODEX_OPS_BRIDGE_STATUS': self.temp.name})
        self.env.start()
        self.value = {'pid': 41, 'shimPid': 42, 'state': 'ready', 'updatedAt': time.time(), 'compressionEnabled': True, 'nativeHostPid': 43, 'counters': {}}
        self.write()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def write(self):
        (Path(self.temp.name) / '42.json').write_text(json.dumps(self.value))

    def test_verified_bridge_switches_to_ordinary_text_guidance(self):
        self.assertTrue(runtime_status.current()['activeForThisProcess'])
        guidance = hook.process({'hook_event_name': 'SessionStart'})['hookSpecificOutput']['additionalContext']
        self.assertIn('use ordinary text()', guidance)
        self.assertNotIn('ops_capture', guidance)

    def test_unknown_host_and_stale_or_wrong_process_fall_back(self):
        for key, value in [('compressionEnabled', False), ('updatedAt', time.time() - 20), ('shimPid', 99), ('state', 'stopped')]:
            saved = self.value[key]
            self.value[key] = value
            self.write()
            self.assertFalse(runtime_status.current()['activeForThisProcess'])
            self.assertIn('ops_capture', hook.process({'hook_event_name': 'SessionStart'})['hookSpecificOutput']['additionalContext'])
            self.value[key] = saved

    def test_missing_or_unattached_manager_is_inactive(self):
        for value in ['', '../other', '99']:
            with patch.dict(os.environ, {'CODEX_OPS_BRIDGE_SHIM_PID': value}):
                self.assertFalse(runtime_status.current()['activeForThisProcess'])

    def test_filtered_mcp_environment_uses_actual_ancestry(self):
        self.value['shimPid'] = 123
        self.write()
        with patch.dict(os.environ, {'CODEX_OPS_AUTO_OUTPUT': '', 'CODEX_OPS_BRIDGE_SHIM_PID': ''}):
            with patch.object(runtime_status, 'ancestors', return_value={123, 456}):
                self.assertTrue(runtime_status.current()['activeForThisProcess'])
            with patch.object(runtime_status, 'ancestors', return_value={789}):
                self.assertFalse(runtime_status.current()['activeForThisProcess'])


if __name__ == '__main__':
    unittest.main()
