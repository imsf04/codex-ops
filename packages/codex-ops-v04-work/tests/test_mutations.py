"""Real native worker tests for planning, CAS publication and recovery."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from mutations import plan, summary
from mutations import cli, engine, journal, paths, planning, worker


def operation(kind, **args):
    return {'operation': kind, 'args': args}


class MutationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, name, value=b'original'):
        (self.root / name).write_bytes(value)
        return self.root / name

    def prepare(self, *operations):
        return plan(str(self.root), list(operations))

    def test_all_six_native_operations_and_exact_rollback(self):
        originals = {'write.txt': b'old\r\n', 'edit.txt': b'alpha beta', 'replace.txt': b'x x',
                     'copy.bin': b'\x00\xff', 'move.bin': b'\xff\x00', 'remove.bin': b'\x01\xfe'}
        for name, data in originals.items():
            self.write(name, data)
        value = self.prepare(operation('write', path='write.txt', content='new\r\n'),
                             operation('edit', path='edit.txt', edits=[{'oldText': 'alpha', 'newText': 'gamma'}]),
                             operation('replace', path='replace.txt', oldText='x', newText='z', expectedCount=2),
                             operation('copy', path='copy.bin', to='copied.bin'),
                             operation('move', path='move.bin', to='moved.bin'), operation('remove', path='remove.bin'))
        self.assertFalse((self.root / paths.RESERVED).exists())
        self.assertEqual(summary(value)['operationCount'], 6)
        result = engine.apply(value)
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(result['after'], 6)
        self.assertEqual((self.root / 'replace.txt').read_bytes(), b'z z')
        self.assertEqual((self.root / 'copied.bin').read_bytes(), originals['copy.bin'])
        self.assertFalse((self.root / 'move.bin').exists())
        self.assertFalse((self.root / 'remove.bin').exists())
        restored = engine.rollback(str(self.root), result['journalId'])
        self.assertEqual(restored['status'], 'rolled-back', restored)
        self.assertEqual(restored['effectState'], 'none')
        self.assertTrue(restored['rollbackComplete'])
        for name, data in originals.items():
            self.assertEqual((self.root / name).read_bytes(), data)
        self.assertFalse((self.root / 'copied.bin').exists())
        self.assertFalse((self.root / 'moved.bin').exists())
        with self.assertRaises(paths.Conflict):
            engine.resume(str(self.root), result['journalId'])

    def test_create_and_noop_and_disjoint_preflight(self):
        self.write('same', b'unchanged')
        value = self.prepare(operation('write', path='new', content='created'), operation('write', path='same', content='unchanged'))
        result = engine.apply(value)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(engine.inspect(str(self.root), result['journalId'])['after'], 1)
        self.assertEqual(engine.rollback(str(self.root), result['journalId'])['status'], 'rolled-back')
        self.assertFalse((self.root / 'new').exists())
        with self.assertRaises(paths.Conflict):
            self.prepare(operation('copy', path='same', to='other'), operation('remove', path='same'))

    def test_stale_second_file_rejects_entire_batch(self):
        self.write('a'); self.write('b')
        value = self.prepare(operation('write', path='a', content='new'), operation('remove', path='b'))
        self.write('b', b'external')
        with self.assertRaises(paths.Conflict):
            engine.apply(value)
        self.assertEqual((self.root / 'a').read_bytes(), b'original')
        self.assertFalse((self.root / paths.RESERVED).exists())

    def test_failure_between_operations_resumes_without_repeating(self):
        self.write('a'); self.write('b')
        value = self.prepare(operation('remove', path='a'), operation('remove', path='b'))
        native = worker.invoke
        def fail_second(root, tool, args, internal=False):
            if args['path'] == 'b':
                raise OSError('injected interruption')
            return native(root, tool, args, internal)
        with patch.object(worker, 'invoke', side_effect=fail_second):
            result = engine.apply(value)
        self.assertEqual(result['status'], 'needs-inspection')
        self.assertEqual(result['after'], 1)
        restored = engine.resume(str(self.root), result['journalId'])
        self.assertEqual(restored['status'], 'completed', restored)
        self.assertFalse((self.root / 'b').exists())
        self.assertEqual(engine.resume(str(self.root), result['journalId'])['status'], 'completed')

    def test_crash_after_publication_is_recovered_from_postconditions(self):
        self.write('a')
        value = self.prepare(operation('remove', path='a'))
        native = worker.invoke
        def crash(root, tool, args, internal=False):
            native(root, tool, args, internal)
            raise KeyboardInterrupt()
        with patch.object(worker, 'invoke', side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                engine.apply(value)
        job = next(p for p in (self.root / paths.RESERVED).iterdir() if p.is_dir())
        self.assertEqual(engine.resume(str(self.root), job.name)['status'], 'completed')

    def test_partial_move_and_partial_rollback(self):
        self.write('a', b'\x00\xff')
        value = self.prepare(operation('move', path='a', to='b'))
        native = worker.invoke
        def interrupt_move(root, tool, args, internal=False):
            native(root, 'copy', args, internal)
            raise subprocess.TimeoutExpired('worker', 32)
        with patch.object(worker, 'invoke', side_effect=interrupt_move):
            result = engine.apply(value)
        self.assertEqual(result['partial'], 1)
        self.assertEqual(engine.resume(str(self.root), result['journalId'])['status'], 'completed')
        def interrupt_remove(root, tool, args, internal=False):
            if tool == 'remove':
                raise OSError('rollback interrupted')
            return native(root, tool, args, internal)
        with patch.object(worker, 'invoke', side_effect=interrupt_remove):
            partial = engine.rollback(str(self.root), result['journalId'])
        self.assertEqual(partial['partial'], 1)
        with self.assertRaises(paths.Conflict):
            engine.resume(str(self.root), result['journalId'])
        self.assertEqual(engine.rollback(str(self.root), result['journalId'])['status'], 'rolled-back')
        self.assertEqual((self.root / 'a').read_bytes(), b'\x00\xff')

    def test_rollback_refuses_external_changes_and_damaged_backup(self):
        self.write('a')
        result = engine.apply(self.prepare(operation('write', path='a', content='new')))
        self.write('a', b'external')
        rejected = engine.rollback(str(self.root), result['journalId'])
        self.assertEqual(rejected['conflicts'], 1)
        self.assertEqual((self.root / 'a').read_bytes(), b'external')
        self.write('a', b'new')
        (self.root / paths.RESERVED / result['journalId'] / '0.bin').write_bytes(b'bad backup')
        rejected = engine.rollback(str(self.root), result['journalId'])
        self.assertEqual(rejected['status'], 'needs-inspection')
        self.assertEqual((self.root / 'a').read_bytes(), b'new')

    def test_paths_roots_and_reserved_directory(self):
        self.write('a')
        bad_paths = ['../outside', '.env', '.dsh-ops/file', paths.RESERVED + '/file', 'missing/file', '.']
        for name in bad_paths:
            with self.subTest(name=name), self.assertRaises(paths.Conflict):
                self.prepare(operation('write', path=name, content='x'))
        with self.assertRaises(paths.Conflict):
            plan('.', [operation('remove', path='a')])
        (self.root / paths.RESERVED).mkdir()
        with self.assertRaises(paths.Conflict):
            engine.apply(self.prepare(operation('remove', path='a')))
        self.assertTrue((self.root / 'a').exists())

    def test_hardlink_and_directory_are_rejected(self):
        self.write('a')
        os.link(self.root / 'a', self.root / 'alias')
        with self.assertRaises(paths.Conflict):
            self.prepare(operation('remove', path='a'))
        (self.root / 'directory').mkdir()
        with self.assertRaises(paths.Conflict):
            self.prepare(operation('remove', path='directory'))

    def test_invalid_operation_shapes_and_text_edit_conflicts(self):
        self.write('a', b'aaaa')
        invalid = [[], [operation('unknown', path='a')], [{'operation': 'remove'}],
                   [operation('remove', path='a', extra=True)], [operation('remove', path='missing')],
                   [operation('copy', path='a', to='a')], [operation('write', path='a', content=3)],
                   [operation('replace', path='a', oldText='a', newText='b', expectedCount=2)],
                   [operation('replace', path='a', oldText='', newText='b', expectedCount=1)],
                   [operation('edit', path='a', edits=[])],
                   [operation('edit', path='a', edits=[{'oldText': 'aa', 'newText': 'b'}])]]
        for operations in invalid:
            with self.subTest(operations=operations), self.assertRaises((paths.Conflict, TypeError)):
                plan(str(self.root), operations)
        self.write('a', b'abcd')
        with self.assertRaises(paths.Conflict):
            self.prepare(operation('edit', path='a', edits=[{'oldText': 'abc', 'newText': 'x'}, {'oldText': 'bcd', 'newText': 'y'}]))

    def test_bounded_files_and_utf8(self):
        self.write('a', b'\xff')
        with self.assertRaises(paths.Conflict):
            self.prepare(operation('write', path='a', content='new'))
        with self.assertRaises(paths.Conflict):
            self.prepare(operation('write', path='new', content='x' * (paths.MAX_BYTES + 1)))
        self.write('large', b'x' * (paths.MAX_BYTES + 1))
        with self.assertRaises(paths.Conflict):
            self.prepare(operation('remove', path='large'))

    def test_digest_and_plan_shape_reject_tampering(self):
        self.write('a')
        value = self.prepare(operation('remove', path='a'))
        value['items'][0]['args']['path'] = '../outside'
        with self.assertRaises(paths.Conflict):
            engine.apply(value)
        value['planDigest'] = paths.digest(planning.encoded({k: value[k] for k in ('version', 'root', 'items')}))
        with self.assertRaises(paths.Conflict):
            engine.apply(value)
        with self.assertRaises(paths.Conflict):
            planning.validate({})
        with self.assertRaises(paths.Conflict):
            engine.inspect(str(self.root), '../bad')

    def test_backup_failure_and_worker_errors_preserve_files(self):
        self.write('a')
        value = self.prepare(operation('remove', path='a'))
        with patch.object(journal, 'read', return_value=b'changed'):
            with self.assertRaises(paths.Conflict):
                journal.create(value)
        with patch.object(worker.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, b'', b'')):
            result = engine.apply(value)
        self.assertEqual(result['status'], 'needs-inspection')
        self.assertTrue((self.root / 'a').exists())
        fake = subprocess.CompletedProcess([], 0, b'{"status":"error","error":{"code":"POLICY_DENIED"}}', b'')
        with patch.object(worker.subprocess, 'run', return_value=fake):
            self.assertEqual(engine.resume(str(self.root), result['journalId'])['status'], 'needs-inspection')

    def test_native_cli_plan_apply_status_and_rollback(self):
        request = self.root / 'request.json'
        request.write_text(json.dumps([operation('write', path='new', content='hello')]))
        output = self.root / 'plan.json'
        def call(args):
            stream = io.StringIO()
            with redirect_stdout(stream):
                cli.main(args)
            return json.loads(stream.getvalue())
        self.assertEqual(call(['plan', '--root', str(self.root), '--request', str(request), '--output', str(output)])['status'], 'planned')
        self.assertEqual(call(['plan', '--root', str(self.root), '--request', str(request), '--output', str(output)])['status'], 'error')
        applied = call(['apply', '--plan', str(output)])
        self.assertEqual(applied['status'], 'completed')
        self.assertEqual(call(['status', '--root', str(self.root), '--id', applied['journalId']])['after'], 1)
        self.assertEqual(call(['rollback', '--root', str(self.root), '--id', applied['journalId']])['status'], 'rolled-back')

    def test_cached_plan_executes_only_through_native_cli(self):
        from store import Store
        value = self.prepare(operation('write', path='new', content='cached'))
        with patch.dict(os.environ, {'CODEX_OPS_STORE': str(self.root / 'cache')}):
            store = Store()
            try:
                receipt = store.capture(value, force=True)
            finally:
                store.close()
            self.assertFalse((self.root / 'new').exists())
            output = io.StringIO()
            with redirect_stdout(output):
                cli.main(['apply', '--plan-ref', receipt['ref']])
            self.assertEqual(json.loads(output.getvalue())['status'], 'completed')
            self.assertEqual((self.root / 'new').read_text(), 'cached')

    def test_real_process_death_releases_lock_and_resume_skips_committed_item(self):
        self.write('a'); self.write('b')
        value = self.prepare(operation('remove', path='a'), operation('remove', path='b'))
        plan_file = self.root / 'plan.json'
        plan_file.write_text(json.dumps(value))
        script = """import json,os,sys
from mutations import engine,worker
native=worker.invoke
def terminate(root,tool,args,internal=False):
    native(root,tool,args,internal)
    os._exit(27)
worker.invoke=terminate
engine.apply(json.load(open(sys.argv[1])))
"""
        child = subprocess.run([sys.executable, '-c', script, str(plan_file)], capture_output=True, timeout=20)
        self.assertEqual(child.returncode, 27, child.stderr)
        self.assertFalse((self.root / 'a').exists())
        self.assertTrue((self.root / 'b').exists())
        job = next(p for p in (self.root / paths.RESERVED).iterdir() if p.is_dir())
        self.assertEqual(engine.resume(str(self.root), job.name)['status'], 'completed')
        self.assertFalse((self.root / 'b').exists())

    def test_journal_lock_rejects_second_owner_then_releases(self):
        self.write('a')
        directory, record = journal.create(self.prepare(operation('remove', path='a')))
        self.assertEqual(engine.receipt(self.root, record)['effectState'], 'none')
        with journal.locked(self.root, directory):
            with self.assertRaises(OSError):
                with journal.locked(self.root, directory):
                    self.fail('Concurrent owner acquired the lock')
        with journal.locked(self.root, directory):
            self.assertTrue((directory / 'lock').exists())

    def test_cli_process_failed_preflight_returns_nonzero(self):
        command = [sys.executable, str(Path(cli.__file__).with_name('__main__.py')), 'apply', '--plan', str(self.root / 'missing')]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['status'], 'error')
        self.assertEqual(cli._exitcode('apply', {'status': 'applying'}), 1)
        self.assertEqual(cli._exitcode('status', {'status': 'applying'}), 0)
        self.assertEqual(cli._exitcode('status', {'status': 'completed', 'conflicts': 1}), 1)


if __name__ == '__main__':
    unittest.main()
