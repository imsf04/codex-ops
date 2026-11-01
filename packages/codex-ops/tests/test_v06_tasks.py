"""Staged native tasks: exact recovery, boundaries and interrupted processes."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import task_api
import task_snapshot
from mutations import engine, journal, paths, task_cli, task_directories, task_engine
from mutations import task_execution, task_journal, task_planning, task_tree

ROOT = Path(__file__).resolve().parents[1]


def op(name, **args):
    return {'operation': name, 'args': args}


class StagedTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def plan(self, *stages):
        return task_api.plan(str(self.root), list(stages))

    def write(self, name, text='old'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def test_all_file_operations_dependent_stages_exact_native_rollback(self):
        self.write('a', 'alpha alpha')
        plan = self.plan([op('replace', path='a', oldText='alpha', newText='beta', expectedCount=2)],
                         [op('edit', path='a', edits=[{'oldText': 'beta beta', 'newText': 'gamma'}]),
                          op('copy', path='a', to='b')],
                         [op('move', path='b', to='c'), op('remove', path='c')],
                         [op('write', path='d', content='rebuilt')])
        self.assertFalse((self.root / task_tree.RESERVED).exists())
        self.assertEqual(task_api.summary(plan)['stageCount'], 4)
        events = []
        result = task_engine.apply(plan, started=events.append)
        self.assertEqual(events[0]['effectState'], 'none')
        self.assertEqual(result['status'], 'completed', result)
        self.assertFalse((self.root / 'c').exists())
        self.assertEqual((self.root / 'a').read_text(), 'gamma')
        self.assertEqual((self.root / 'd').read_text(), 'rebuilt')
        self.assertEqual(task_engine.inspect(self.root, result['taskId'])['completedSteps'], 6)
        restored = task_engine.rollback(self.root, result['taskId'])
        self.assertTrue(restored['rollbackComplete'], restored)
        self.assertEqual((self.root / 'a').read_text(), 'alpha alpha')
        self.assertFalse((self.root / 'b').exists() or (self.root / 'c').exists() or (self.root / 'd').exists())
        self.assertEqual(task_engine.resume(self.root, result['taskId'])['status'], 'needs-inspection')

    def test_directory_copy_move_remove_and_empty_directories_roundtrip(self):
        self.write('src/sub/a', 'content')
        (self.root / 'src/empty').mkdir()
        plan = self.plan([op('copy_tree', path='src', to='copy')],
                         [op('write', path='copy/sub/a', content='changed')],
                         [op('move_tree', path='copy', to='moved')],
                         [op('remove_tree', path='src')])
        result = task_engine.apply(plan)
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual((self.root / 'moved/sub/a').read_text(), 'changed')
        self.assertTrue((self.root / 'moved/empty').is_dir())
        self.assertFalse((self.root / 'src').exists())
        restored = task_engine.rollback(self.root, result['taskId'])
        self.assertTrue(restored['rollbackComplete'], restored)
        self.assertEqual((self.root / 'src/sub/a').read_text(), 'content')
        self.assertTrue((self.root / 'src/empty').is_dir())
        self.assertFalse((self.root / 'copy').exists() or (self.root / 'moved').exists())

    def test_cancel_is_cooperative_and_explicit_resume_clears_request(self):
        plan = self.plan([op('write', path='a', content='one'), op('write', path='b', content='two')])
        original = task_execution.execute
        def first_then_cancel(root, folder, record, step):
            original(root, folder, record, step)
            task_engine.cancel(root, record['id'])
        with patch.object(task_execution, 'execute', first_then_cancel):
            result = task_engine.apply(plan)
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(result['completedSteps'], 1)
        self.assertFalse((self.root / 'b').exists())
        resumed = task_engine.resume(self.root, result['taskId'])
        self.assertEqual(resumed['status'], 'completed')
        self.assertTrue(task_engine.rollback(self.root, result['taskId'])['rollbackComplete'])

    def test_cancel_before_any_effect_and_status_summary_are_readable(self):
        plan = self.plan([op('mkdir', path='new')], [op('mkdir', path='new/sub')])
        def cancel(event):
            task_engine.cancel(self.root, event['taskId'])
        result = task_engine.apply(plan, started=cancel)
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(result['effectState'], 'none')
        self.assertFalse((self.root / 'new').exists())
        snapshot = task_snapshot.snapshot(str(self.root))
        staged = next(row for row in snapshot['items'] if row['taskKind'] == 'staged')
        self.assertEqual(staged['completedSteps'], 0)
        self.assertEqual(staged['stageCount'], 2)
        self.assertEqual(task_engine.resume(self.root, result['taskId'])['status'], 'completed')
        (self.root / 'new/sub/unexpected').write_text('external')
        rejected = task_engine.rollback(self.root, result['taskId'])
        self.assertEqual(rejected['status'], 'needs-inspection')
        self.assertTrue((self.root / 'new/sub/unexpected').exists())

    def test_native_failure_preserves_journal_and_resume_does_not_repeat_completed_steps(self):
        plan = self.plan([op('write', path='a', content='one'), op('write', path='b', content='two')])
        original = task_execution.execute
        calls = []
        def failure(root, folder, record, step):
            calls.append(step['args']['path'])
            if len(calls) == 2:
                raise PermissionError('native permission denied')
            return original(root, folder, record, step)
        with patch.object(task_execution, 'execute', failure):
            result = task_engine.apply(plan)
        self.assertEqual(result['status'], 'needs-inspection')
        self.assertEqual(result['completedSteps'], 1)
        (self.root / 'a').write_text('external')
        denied = task_engine.resume(self.root, result['taskId'])
        self.assertEqual(denied['status'], 'needs-inspection')
        self.assertFalse((self.root / 'b').exists())
        (self.root / 'a').write_text('one')
        self.assertEqual(task_engine.resume(self.root, result['taskId'])['status'], 'completed')

    def test_completion_before_parent_checkpoint_is_reconciled_without_replay(self):
        plan = self.plan([op('write', path='a', content='one'), op('write', path='b', content='two')])
        original = task_execution.execute
        def interrupted(root, folder, record, step):
            original(root, folder, record, step)
            raise RuntimeError('simulated abrupt control loss')
        with patch.object(task_execution, 'execute', interrupted):
            with self.assertRaises(RuntimeError):
                task_engine.apply(plan)
        identity = next(p.name for p in (self.root / task_tree.RESERVED).iterdir() if p.is_dir())
        self.assertFalse(task_engine.inspect(self.root, identity)['frontierMatches'])
        result = task_engine.resume(self.root, identity)
        self.assertEqual(result['status'], 'completed', result)
        self.assertTrue(task_engine.rollback(self.root, identity)['rollbackComplete'])

    def test_killed_native_process_releases_lock_and_resumes_exactly(self):
        plan = self.plan([op('write', path='a', content='one'), op('write', path='b', content='two')])
        path = self.root / 'plan.json'
        path.write_text(json.dumps(plan))
        script = """
import json,os,sys
from pathlib import Path
from mutations import task_engine,task_execution
original=task_execution.execute
def stop(root,folder,record,step):
    original(root,folder,record,step)
    os._exit(73)
task_execution.execute=stop
task_engine.apply(json.loads(Path(sys.argv[1]).read_text()))
"""
        run = subprocess.run([sys.executable, '-c', script, str(path)], cwd=ROOT, capture_output=True, timeout=40)
        self.assertEqual(run.returncode, 73, run.stderr)
        identity = next(p.name for p in (self.root / task_tree.RESERVED).iterdir() if p.is_dir())
        self.assertEqual(task_engine.resume(self.root, identity)['status'], 'completed')
        self.assertTrue(task_engine.rollback(self.root, identity)['rollbackComplete'])

    def _killed_partial_move(self, folder):
        folder.mkdir()
        (folder / 'a').write_text('original')
        (folder / 'guard').write_text('unchanged')
        plan = task_api.plan(str(folder), [[op('move', path='a', to='b')],
                                         [op('write', path='guard', content='updated')]])
        request, signal = folder / 'plan.json', folder / 'partial-ready'
        request.write_text(json.dumps(plan))
        script = '''
import json,sys,time
from pathlib import Path
from mutations import task_engine,worker
def partial(root,tool,args,*rest,**kwargs):
    assert tool == 'move'
    (root/args['to']).write_bytes((root/args['path']).read_bytes())
    Path(sys.argv[2]).write_text('copy published; source not yet removed')
    time.sleep(60)
worker.invoke=partial
task_engine.apply(json.loads(Path(sys.argv[1]).read_text()))
'''
        process = subprocess.Popen([sys.executable, '-c', script, str(request), str(signal)],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 15
            while not signal.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(signal.exists(), 'Child did not reach the controlled move-copy boundary')
        finally:
            process.terminate()
            process.communicate(timeout=10)
        identity = next(p.name for p in (folder / task_tree.RESERVED).iterdir() if p.is_dir())
        return identity

    def test_process_kill_inside_move_supports_explicit_resume_and_rollback(self):
        for action in ('resume', 'rollback'):
            with self.subTest(action=action):
                folder = self.root / action
                identity = self._killed_partial_move(folder)
                state = task_engine.inspect(folder, identity)
                self.assertFalse(state['frontierMatches'])
                self.assertIsNotNone(state['activeChildJournal'])
                result = getattr(task_engine, action)(folder, identity)
                self.assertEqual(result['status'], 'completed' if action == 'resume' else 'rolled-back', result)
                if action == 'resume':
                    self.assertFalse((folder / 'a').exists())
                    self.assertEqual((folder / 'b').read_text(), 'original')
                    self.assertEqual((folder / 'guard').read_text(), 'updated')
                    self.assertTrue(task_engine.rollback(folder, identity)['rollbackComplete'])
                self.assertEqual((folder / 'a').read_text(), 'original')
                self.assertFalse((folder / 'b').exists())
                self.assertEqual((folder / 'guard').read_text(), 'unchanged')

    def test_partial_child_recovery_rejects_changed_other_paths(self):
        folder = self.root / 'partial'
        identity = self._killed_partial_move(folder)
        (folder / 'guard').write_text('external')
        for action in ('resume', 'rollback'):
            with patch('mutations.worker.invoke') as invoke:
                result = getattr(task_engine, action)(folder, identity)
                self.assertEqual(result['status'], 'needs-inspection')
                self.assertIn('outside the interrupted child changed', result['error'])
                invoke.assert_not_called()
        self.assertEqual((folder / 'guard').read_text(), 'external')
        self.assertTrue((folder / 'a').exists() and (folder / 'b').exists())

    def test_child_conflict_is_not_treated_as_recoverable_partial_move(self):
        folder = self.root / 'partial'
        identity = self._killed_partial_move(folder)
        (folder / 'b').write_text('external')
        result = task_engine.resume(folder, identity)
        self.assertEqual(result['status'], 'needs-inspection')
        self.assertIn('conflicting file content', result['error'])
        self.assertEqual((folder / 'b').read_text(), 'external')

    def test_interrupted_partial_recovery_retains_explicit_rollback_direction(self):
        folder = self.root / 'partial'
        identity = self._killed_partial_move(folder)
        from mutations import worker
        original = worker.invoke
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('lost after child rollback effect')
        with patch.object(worker, 'invoke', interrupted):
            with self.assertRaisesRegex(RuntimeError, 'lost after child'):
                task_engine.rollback(folder, identity)
        state = task_engine.inspect(folder, identity)
        self.assertEqual(state['direction'], 'rollback')
        self.assertIsNotNone(state['activeChildJournal'])
        self.assertEqual(task_engine.resume(folder, identity)['status'], 'needs-inspection')
        self.assertTrue(task_engine.rollback(folder, identity)['rollbackComplete'])

    def test_partial_rollback_of_completed_move_recovers_tracked_child(self):
        self.write('a', 'original')
        result = task_engine.apply(self.plan([op('move', path='a', to='b')]))
        from mutations import worker
        original = worker.invoke
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('lost after source restoration')
        with patch.object(worker, 'invoke', interrupted):
            with self.assertRaisesRegex(RuntimeError, 'lost after source'):
                task_engine.rollback(self.root, result['taskId'])
        self.assertTrue((self.root / 'a').exists() and (self.root / 'b').exists())
        self.assertTrue(task_engine.rollback(self.root, result['taskId'])['rollbackComplete'])
        self.assertEqual((self.root / 'a').read_text(), 'original')
        self.assertFalse((self.root / 'b').exists())

    def test_rollback_after_child_completed_before_parent_checkpoint(self):
        plan = self.plan([op('mkdir', path='new')], [op('write', path='new/a', content='one')])
        result = task_engine.apply(plan)
        original = task_execution.reverse
        def stop(root, folder, record, step, index):
            original(root, folder, record, step, index)
            raise RuntimeError('rollback interruption')
        with patch.object(task_execution, 'reverse', stop):
            with self.assertRaises(RuntimeError):
                task_engine.rollback(self.root, result['taskId'])
        self.assertTrue(task_engine.rollback(self.root, result['taskId'])['rollbackComplete'])

    def test_plan_validation_and_path_tree_limits(self):
        self.write('src/a')
        cases = [[], [[]], [list(op('write', path='a', content='x') for _ in range(33))],
                 [[{'operation': 'x', 'args': {}}]], [[{'operation': 'write', 'args': {}}]],
                 [[op('write', path='../escape', content='x')]],
                 [[op('write', path='C:escape', content='x')]],
                 [[op('write', path='file:stream', content='x')]],
                 [[op('write', path='nul.txt', content='x')]],
                 [[op('write', path='name.', content='x')]],
                 [[op('write', path='name ', content='x')]],
                 [[op('write', path='.env', content='x')]],
                 [[op('write', path='.codex-ops-tasks/x', content='x')]],
                 [[op('write', path='missing/a', content='x')]],
                 [[op('rmdir', path='src')]], [[op('copy_tree', path='src', to='src/sub')]],
                 [[op('copy_tree', path='src', to='src')]], [[op('remove_tree', path='src/a')]],
                 [[op('write', path='src', content='x')]], [[op('copy', path='src/a', to='src/a')]]]
        cases.append([[op('write', path='New', content='x'), op('write', path='new', content='y')]])
        for stages in cases:
            with self.subTest(stages=stages):
                with self.assertRaises((ValueError, TypeError)):
                    task_api.plan(str(self.root), stages)
        with patch.object(task_tree, 'MAX_NODES', 1):
            with self.assertRaises(ValueError):
                self.plan([op('remove_tree', path='src')])
        with patch.object(task_tree, 'MAX_TOTAL_BYTES', 1):
            with self.assertRaises(ValueError):
                self.plan([op('remove_tree', path='src')])
        with self.assertRaises(ValueError):
            task_planning.validate({})
        plan = self.plan([op('write', path='new', content='x')])
        plan['planDigest'] = 'invalid'
        with self.assertRaises(ValueError):
            task_engine.apply(plan)

    def test_plan_cas_and_unowned_journals_reject_before_effect(self):
        self.write('a')
        plan = self.plan([op('write', path='a', content='new')])
        self.write('a', 'changed')
        with self.assertRaises(ValueError):
            task_engine.apply(plan)
        self.assertFalse((self.root / task_tree.RESERVED).exists())
        (self.root / task_tree.RESERVED).mkdir()
        (self.root / task_tree.RESERVED / 'owner.json').write_text('{}')
        with self.assertRaises(ValueError):
            task_engine.apply(self.plan([op('write', path='a', content='new')]))

    def test_reserved_tasks_and_future_parent_paths_are_not_mutable_via_legacy_plans(self):
        from mutations import plan as legacy
        with self.assertRaises(ValueError):
            legacy(str(self.root), [op('write', path='.codex-ops-tasks', content='bad')])
        with self.assertRaises(ValueError):
            self.plan([op('write', path='missing/.env', content='secret')])
        with self.assertRaises(ValueError):
            self.plan([op('write', path='missing/.dsh-ops/file', content='bad')])
        with self.assertRaises(ValueError):
            self.plan([op('write', path='missing/.codex-ops-mutations/file', content='bad')])

    def test_parent_handle_prevents_rename_and_failure_does_not_create_target(self):
        folder = self.root / 'stable'
        folder.mkdir()
        with task_directories._hold(folder):
            with self.assertRaises(OSError):
                folder.rename(self.root / 'renamed')
        with self.assertRaises(OSError):
            with task_directories._hold(self.root / 'absent'):
                self.fail('Expected open failure')
        task_directories.execute(self.root, 'stable/sub', True)
        task_directories.execute(self.root, 'stable/sub', False)
        self.assertFalse((folder / 'sub').exists())

    def test_native_cli_and_argv_do_not_execute_from_planning(self):
        plan = self.plan([op('write', path='a', content='one')])
        path = self.root / 'plan.json'
        path.write_text(json.dumps(plan))
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(task_cli.main(['apply', '--plan', str(path)]), 0)
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        identity = rows[-1]['taskId']
        self.assertEqual(rows[0]['status'], 'started')
        command = task_api.command('status', str(self.root), identity)
        result = subprocess.run([command['executable'], *command['args']], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'completed')
        self.assertIn('--plan-ref', task_api.command('apply', reference='ops://' + 'a' * 48)['args'])
        for name, invalid_identity in [('unknown', identity), ('resume', 'bad')]:
            with self.assertRaises(ValueError):
                task_api.command(name, str(self.root), invalid_identity)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(task_cli.main(['status', '--root', str(self.root), '--id', 'bad']), 1)
        self.assertTrue(task_engine.rollback(self.root, identity)['rollbackComplete'])


if __name__ == '__main__':
    unittest.main()
