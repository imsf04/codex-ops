import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import runtime_status
import session_scope
from store import Store, ReferenceUnavailable


class RuntimeDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.active = {'shimPid': 300, 'pid': 301, 'nativeHostPid': 302, 'state': 'ready',
                       'updatedAt': time.time(), 'runtimeVersion': '0.6.1',
                       'compressionEnabled': True, 'counters': {}}
        self.write('active', self.active)
        environment = patch.dict(os.environ, {'CODEX_OPS_AUTO_OUTPUT': '', 'CODEX_OPS_BRIDGE_SHIM_PID': '',
                                              'CODEX_OPS_BRIDGE_STATUS': str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        ancestry = patch.object(runtime_status, 'ancestors', return_value=[100, 200, 300, 400])
        ancestry.start()
        self.addCleanup(ancestry.stop)

    def write(self, name, value):
        (self.root / (name + '.json')).write_text(json.dumps(value), encoding='utf-8')

    def test_stale_reused_process_pid_cannot_hide_actual_ancestor_runtime(self):
        self.write('reused', {**self.active, 'shimPid': 100, 'pid': 999, 'updatedAt': time.time() - 3600})
        selected = runtime_status.current()
        self.assertTrue(selected['activeForThisProcess'])
        self.assertEqual(selected['managerPid'], 301)
        cache = Store(self.root / 'cache')
        try:
            original = 'exact runtime-owned value ' * 1000
            with session_scope.bind(session_scope.for_runtime(301)):
                receipt = cache.capture(original)
            caller = session_scope.from_meta({'threadId': '11111111-1111-1111-1111-111111111111'}, str(selected['managerPid']))
            with session_scope.bind(caller):
                self.assertEqual(cache.get(receipt['ref']), original)
            with session_scope.bind(session_scope.for_runtime(999)):
                with self.assertRaises(ReferenceUnavailable):
                    cache.get(receipt['ref'])
        finally:
            cache.close()

    def test_stopped_and_missing_timestamp_candidates_do_not_shadow_ready_ancestor(self):
        self.write('stopped', {**self.active, 'shimPid': 100, 'state': 'stopped'})
        self.write('malformed', {**self.active, 'shimPid': 200, 'updatedAt': 'not-a-timestamp'})
        self.assertEqual(runtime_status.current()['managerPid'], 301)

    def test_unrelated_fresh_runtime_never_grants_access_when_ancestors_are_stale(self):
        self.write('active', {**self.active, 'updatedAt': time.time() - 30})
        self.write('unrelated', {**self.active, 'shimPid': 555, 'pid': 556})
        self.assertFalse(runtime_status.current()['activeForThisProcess'])


if __name__ == '__main__':
    unittest.main()
