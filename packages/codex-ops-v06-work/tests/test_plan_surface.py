import os
from pathlib import Path
import tempfile
import unittest

from unittest.mock import patch
import server
from store import Store


class PlanSurfaceTests(unittest.TestCase):
    def test_read_only_surface_saves_plan_and_returns_native_execution_route(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'CODEX_OPS_STORE': temp + '/cache'}):
            root = Path(temp)
            (root / 'a.txt').write_text('before')
            receipt = server.ops_plan(str(root), [{'operation': 'write', 'args': {'path': 'a.txt', 'content': 'after'}}])
            self.assertEqual((root / 'a.txt').read_text(), 'before')
            self.assertFalse((root / '.codex-ops-mutations').exists())
            self.assertEqual(receipt['kind'], 'reference')
            self.assertEqual(receipt['preview']['operationCount'], 1)
            self.assertEqual(receipt['nativeExecution']['args'][-1], receipt['ref'])
            saved = Store()
            self.assertEqual(saved.get(receipt['ref'])['items'][0]['args']['content'], 'after')
            saved.close()

    def test_plan_failure_and_storage_failure_remain_no_workspace_effect(self):
        self.assertEqual(server.ops_plan('relative', [])['error']['code'], 'PLAN_REJECTED')
        with patch.object(server, 'mutation_plan', return_value={'items': []}), patch.object(server, 'Store') as cls:
            cls.return_value.capture.return_value = {'status': 'error'}
            self.assertEqual(server.ops_plan('unused', []), {'status': 'error'})

    def test_result_new_views_route_through_meter_without_mutating_observation(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'CODEX_OPS_STORE': temp}):
            ref = server.ops_capture({'records': ['needle' * 1000] * 4})['ref']
            self.assertEqual(server.ops_result(ref, view='outline')['items'][0]['path'], '/records')
            found = server.ops_result(ref, view='find', query='needle')
            self.assertEqual(found['items'][0]['path'], '/records/0')


if __name__ == '__main__':
    unittest.main()
