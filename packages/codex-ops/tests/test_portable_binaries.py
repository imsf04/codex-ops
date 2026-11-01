import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import files
from mutations import worker


class NativeBinaryPathsTests(unittest.TestCase):
    def test_read_and_investigate_use_platform_native_executables(self):
        suffix = '.exe' if os.name == 'nt' else ''
        completed = subprocess.CompletedProcess([], 0, stdout=b'{"status":"completed"}', stderr=b'')
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {'CODEX_OPS_WORKER': '', 'CODEX_OPS_KERNEL': ''}):
            del os.environ['CODEX_OPS_WORKER']
            del os.environ['CODEX_OPS_KERNEL']
            with patch('files.native_process.run', return_value=completed) as run:
                files._invoke_worker(Path(directory), 'stat', {'path': '.'})
                self.assertEqual(Path(run.call_args.args[0][0]).name, 'dsh-ops-worker' + suffix)
                files._kernel(Path(directory), {})
                self.assertEqual(Path(run.call_args.args[0][0]).name, 'codex-ops-kernel' + suffix)

    def test_mutations_use_platform_native_worker(self):
        suffix = '.exe' if os.name == 'nt' else ''
        completed = subprocess.CompletedProcess([], 0, stdout=b'{"status":"completed"}', stderr=b'')
        with tempfile.TemporaryDirectory() as directory, patch('mutations.worker.subprocess.run', return_value=completed) as run:
            worker.invoke(Path(directory), 'test', {})
            self.assertEqual(Path(run.call_args.args[0][0]).name, 'dsh-ops-worker' + suffix)


if __name__ == '__main__':
    unittest.main()
