import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import files
import investigate
import investigate_plan
import investigate_query
import native_process
import cost_events


class KernelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='codex-ops-kernel-test-')
        self.root = Path(self.temp.name)
        (self.root / 'src').mkdir()
        (self.root / 'tests').mkdir()
        (self.root / 'coverage').mkdir()
        (self.root / 'src/main.py').write_text('CAP = 17\n\ndef clamp(value):\n    return min(value, CAP)\n', encoding='utf-8')
        (self.root / 'tests/test_cap.py').write_text('def test_cap():\n    assert CAP == 17\n', encoding='utf-8')
        (self.root / 'settings.toml').write_text('CAP = 17\n', encoding='utf-8')
        (self.root / 'coverage/noise.json').write_text(json.dumps({'CAP': 'noise'}), encoding='utf-8')
        self.environment = patch.dict(os.environ, {'CODEX_OPS_STORE': str(self.root / '.cache'),
                                                   'CODEX_OPS_MEASUREMENT_ORIGIN': 'validation'})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def run_query(self, **args):
        return investigate.run(str(self.root), args, files.run)

    def test_code_and_tests_and_configuration_are_retrieved_in_one_process(self):
        result = self.run_query(question='Where is CAP implemented, tested and configured?', anchors=['CAP'])
        self.assertIn(result['status'], ('completed', 'partial'))
        paths = {Path(row['source']['path']).name for row in result['items']}
        self.assertIn('main.py', paths)
        self.assertIn('test_cap.py', paths)
        self.assertIn('settings.toml', paths)
        self.assertNotIn('noise.json', paths)
        kernel = result['coverage']['kernel']
        self.assertEqual(kernel['workerStarts'], 1)
        self.assertEqual(kernel['internalOperations'], 6)
        self.assertEqual(kernel['plannedStages'], 3)
        for row in result['items']:
            lines = Path(row['source']['path']).read_text().splitlines()
            self.assertEqual(row['text'], lines[row['location']['line'] - 1])

    def test_explicit_file_scope_is_not_broadened_by_test_intent(self):
        result = self.run_query(question='Find CAP tests and config', anchors=['CAP'], paths=['src/main.py'])
        self.assertEqual(result['coverage']['kernel']['plannedStages'], 1)
        self.assertEqual({Path(row['source']['path']).name for row in result['items']}, {'main.py'})

    def test_focus_changes_native_search_not_only_labels(self):
        definition = investigate_query.parse({'question': 'clamp', 'focus': 'definition'})
        references = investigate_query.parse({'question': 'clamp', 'focus': 'references'})
        (self.root / 'src/caller.py').write_text('value = clamp(99)\n', encoding='utf-8')
        first = files.run(str(self.root), 'investigate', investigate_plan.build(str(self.root), definition))
        second = files.run(str(self.root), 'investigate', investigate_plan.build(str(self.root), references))
        self.assertEqual(len(first['stages'][0]['result']['matches']), 1)
        self.assertEqual(len(second['stages'][0]['result']['matches']), 2)
        config = self.run_query(question='CAP', focus='configuration')
        self.assertEqual({Path(r['source']['path']).name for r in config['items']}, {'settings.toml'})
        failure = self.run_query(question='CAP fails', focus='failure')
        self.assertEqual(failure['coverage']['kernel']['plannedStages'], 2)

    def test_missing_path_and_scope_errors_do_not_become_no_match(self):
        for paths in (['../'], ['absent.py']):
            with self.subTest(paths=paths):
                result = self.run_query(question='CAP', paths=paths)
                self.assertEqual(result['status'], 'error')
                self.assertEqual(result.get('error', {}).get('effectState', 'none'), 'none')
        result = self.run_query(question='CAP', paths=['src/main.py', 'absent.py'])
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(any(stage.get('error') for stage in result['coverage']['stages']))

    def test_process_timeout_kills_child_and_preserves_error(self):
        marker = self.root / 'completed'
        code = 'import pathlib,time; time.sleep(0.6); pathlib.Path(' + repr(str(marker)) + ').write_text("wrong")'
        with self.assertRaises(subprocess.TimeoutExpired):
            native_process.run([sys.executable, '-c', code], b'', 0.1, 'investigate')
        time.sleep(0.7)
        self.assertFalse(marker.exists())
        with patch.dict(os.environ, {'CODEX_OPS_KERNEL': str(self.root / 'absent.exe')}):
            error = self.run_query(question='CAP')
        self.assertEqual(error['error']['code'], 'WORKER_ERROR')

    def test_real_parallel_batch_preserves_native_chat_attribution(self):
        chat = 'chat:01234567-89ab-cdef-0123-456789abcdef'
        requests = {'requests': [{'operation': 'stat', 'args': {'path': 'src/main.py'}},
                                 {'operation': 'stat', 'args': {'path': 'tests/test_cap.py'}}]}
        with cost_events.scope(chat, str(self.root)):
            result = files.run(str(self.root), 'batch', requests)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([row['index'] for row in result['items']], [0, 1])
        measured = cost_events.snapshot(context=chat, origin='validation')
        self.assertEqual(measured['scope'], 'native-chat')
        self.assertEqual(measured['workerStarts'], 2)
        foreign = cost_events.snapshot(context='chat:11234567-89ab-cdef-0123-456789abcdef', origin='validation')
        self.assertEqual(foreign['workerStarts'], 0)

    def test_kernel_invalid_json_exit_and_timeout_have_distinct_failures(self):
        name = 'codex-ops-kernel.exe' if os.name == 'nt' else 'codex-ops-kernel'
        command = Path(os.environ.get('CODEX_OPS_KERNEL', Path(files.__file__).parent / 'bin' / name))
        bad = subprocess.run([str(command)], input=b'invalid', capture_output=True, timeout=5)
        self.assertEqual(bad.returncode, 0)
        self.assertEqual(json.loads(bad.stdout)['status'], 'error')
        version = subprocess.run([str(command), '--version'], capture_output=True, timeout=5)
        self.assertIn(b'0.8.0', version.stdout)
        with patch('files.native_process.run', return_value=subprocess.CompletedProcess([],124,stdout=b'')):
            result = self.run_query(question='CAP')
        self.assertEqual(result['error']['code'], 'WORKER_FAILED')
        self.assertIn('124', result['error']['message'])
        with patch('files.native_process.run', side_effect=subprocess.TimeoutExpired('kernel',32)):
            result = self.run_query(question='CAP')
        self.assertEqual(result['error']['code'], 'WORKER_TIMEOUT')

    def test_native_kernel_deadline_is_real_and_readonly(self):
        source = self.root / 'large.log'
        source.write_bytes(b'ordinary line\n' * 1000000)
        size = source.stat().st_size
        query = investigate_query.parse({'question': 'ABSENT_DEADLINE_SENTINEL', 'paths': ['large.log']})
        envelope = {'version': 1, 'requestId': 'deadline', 'component': 'file',
                    'budget': {'timeoutMs': 1, 'maxBytes': 131072},
                    'request': {'root': str(self.root), 'scope': 'test', 'read_only': True,
                                'deny_credential_names': True, 'tool': 'investigate',
                                'args': investigate_plan.build(str(self.root), query)}}
        name = 'codex-ops-kernel.exe' if os.name == 'nt' else 'codex-ops-kernel'
        command = Path(os.environ.get('CODEX_OPS_KERNEL', Path(files.__file__).parent / 'bin' / name))
        result = subprocess.run([str(command)], input=json.dumps(envelope).encode(), capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 124)
        self.assertEqual(source.stat().st_size, size)


if __name__ == '__main__':
    unittest.main()
