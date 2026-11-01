import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import server
import session_scope
from store import Store

A = '01a18391-1809-7601-96cc-09b2c96329c1'
B = '01a18391-1809-7601-96cc-09b2c96329c2'


def context(identity=A):
    return SimpleNamespace(request_context=SimpleNamespace(meta={'threadId': identity,
        'x-codex-turn-metadata': {'thread_id': identity, 'sandbox_mode': 'workspace-write'}}))


def inline(value):
    return value['value'] if value.get('kind') == 'inline' else value


class PublicToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'CODEX_OPS_STORE': str(self.root / 'cache'), 'CODEX_OPS_MEASUREMENT_ORIGIN': 'validation'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.runtime = patch.object(server.runtime_status, 'current', return_value={'activeForThisProcess': True, 'managerPid': 100, 'runtimeVersion': '0.6.0'})
        self.runtime.start()
        self.addCleanup(self.runtime.stop)

    def test_public_incremental_baseline_is_owned_and_exact_current_content_is_retrievable(self):
        (self.root / 'a.py').write_text('old\nline\n')
        args = {'files': [{'path': 'a.py', 'limit': 20}]}
        first = inline(server.ops_workflow(str(self.root), 'incremental', args, context()))
        self.assertIn('snapshotRef', first)
        (self.root / 'a.py').write_text('new\nline\n')
        args['baselineRef'] = first['snapshotRef']
        second = inline(server.ops_workflow(str(self.root), 'incremental', args, context()))
        self.assertEqual(second['items'][0]['mode'], 'delta')
        self.assertIn('new', json.dumps(second['items'][0]['changes']))
        page = server.ops_result(second['snapshotRef'], view='raw', path='/result', ctx=context())
        self.assertIn('new', page['text'])
        denied = server.ops_result(first['snapshotRef'], ctx=context(B))
        self.assertEqual(denied['error']['code'], 'REFERENCE_UNAVAILABLE')
        self.assertNotIn('old', json.dumps(denied))

    def test_public_task_plan_has_no_effect_and_returns_native_lifecycle(self):
        args = {'stages': [[{'operation': 'mkdir', 'args': {'path': 'result'}}],
            [{'operation': 'write', 'args': {'path': 'result/a.txt', 'content': 'done'}}]]}
        plan = server.ops_task(str(self.root), 'plan', args, context())
        self.assertEqual(plan['kind'], 'reference')
        self.assertEqual(plan['purpose'], 'task-plan')
        self.assertFalse((self.root / 'result').exists())
        self.assertIn('--plan-ref', plan['nativeExecution']['args'])
        for action in ('status', 'resume', 'cancel', 'rollback'):
            result = server.ops_task(str(self.root), action, {'id': '1' * 32}, context())
            self.assertTrue(result['nativeExecution']['requiresNativePermission'])
        self.assertEqual(server.ops_task(str(self.root), 'plan', {'bad': []}, context())['status'], 'error')
        self.assertEqual(server.ops_task(str(self.root), 'cancel', {}, context())['status'], 'error')
        self.assertEqual(server.ops_task(str(self.root), 'destroy', {'id': '1' * 32}, context())['status'], 'error')

    def test_unattributed_library_calls_remain_explicit_and_snapshot_failure_is_not_success(self):
        self.assertIsNone(server._owner(None))
        self.assertEqual(server._owner(SimpleNamespace(request_context=SimpleNamespace(meta={})))['runtime'], '100')
        with patch.object(server.runtime_status, 'current', return_value={}):
            self.assertTrue(server._owner(SimpleNamespace(request_context=SimpleNamespace(meta={})))['runtime'].startswith('mcp:'))
        with session_scope.bind({'runtime': 'unknown'}):
            with self.assertRaisesRegex(ValueError, 'native chat identity'):
                server._require_plan_identity()
        with self.assertRaisesRegex(ValueError, 'could not be saved'):
            server._save_snapshot(SimpleNamespace(capture=lambda *a, **k: {'status': 'error'}), {})
        self.assertEqual(server.ops_workflow(str(self.root), 'unknown', {}, context())['value']['status'], 'error')
        self.assertEqual(server.ops_workflow(str(self.root), 'sdk', {}, context())['value']['operation'], 'sdk')

    def test_large_task_receipt_preserves_executable_and_explicit_omissions(self):
        operations = [{'operation': 'write', 'args': {'path': f'file-{i}.txt', 'content': 'x'}} for i in range(32)]
        result = server.ops_task(str(self.root), 'plan', {'stages': [operations]}, context())
        self.assertEqual(result['preview']['omittedSteps'], 24)
        self.assertEqual(len(result['preview']['steps']), 8)
        self.assertLess(len(json.dumps(result).encode()), 8000)
        from presentation_policy import Presenter
        self.assertEqual(Presenter().render(json.dumps(result)), json.dumps(result))
        import task_preview
        self.assertEqual(task_preview.capture(SimpleNamespace(capture=lambda *a, **k: {'status': 'error'}), {})['status'], 'error')


if __name__ == '__main__':
    unittest.main()
