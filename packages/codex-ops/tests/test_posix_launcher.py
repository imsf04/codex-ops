import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

if os.name == 'nt':
    raise unittest.SkipTest('POSIX launcher is not used on Windows')

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime_bridge'))
import launcher_posix


class PosixLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.cli = self.root / 'codex'
        self.host = self.root / 'codex-code-mode-host'
        self.host.touch()
        cli_script = self.root / 'cli.py'
        cli_script.write_text('import json,os,sys,time\n'
                              'p=os.environ["CLI_STATE"];open(p+".tmp","w").write(json.dumps({"pid":os.getpid(),"args":sys.argv[1:],"env":os.environ.get("CODEX_OPS_AUTO_OUTPUT")}));os.replace(p+".tmp",p)\n'
                              'time.sleep(float(os.environ.get("CLI_SLEEP","0")))\n')
        self.cli.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(cli_script)) + ' "$@"\n')
        self.cli.chmod(0o755)
        self.manager = self.root / 'manager.py'
        self.manager.write_text('import os,time,signal\n'
                                'signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
                                'p=os.environ["MANAGER_STATE"];open(p+".tmp","w").write(str(os.getpid()));os.replace(p+".tmp",p)\n'
                                'print("http://127.0.0.1:12345",flush=True)\n'
                                'time.sleep(60)\n')
        self.env = {key: value for key, value in os.environ.items()
                    if key.lower() not in ('http_proxy', 'https_proxy', 'all_proxy')}
        self.env.update(CLI_STATE=str(self.root / 'cli.json'), MANAGER_STATE=str(self.root / 'manager.pid'))
        self.script = ('import sys;sys.path.insert(0,sys.argv[1]);import launcher_posix;'
                       'launcher_posix.main(sys.argv[4:],cli=sys.argv[2],manager=sys.argv[3])')

    def command(self, *arguments):
        return [sys.executable, '-c', self.script, str(Path(launcher_posix.__file__).parent),
                str(self.cli), str(self.manager), *arguments]

    def wait_for(self, path):
        deadline = time.monotonic() + 10
        while not path.exists():
            if time.monotonic() >= deadline:
                self.fail('Process did not publish its state')
            time.sleep(.02)

    def test_service_injects_host_and_cleans_manager(self):
        subprocess.run(self.command('app-server', '--stdio'), env=self.env, check=True, timeout=15)
        state = json.loads((self.root / 'cli.json').read_text())
        self.assertEqual(state['args'], ['app-server', '--code-mode-host', 'http://127.0.0.1:12345', '--stdio'])
        self.assertEqual(state['env'], '1')
        pid = int((self.root / 'manager.pid').read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_killing_launcher_cleans_owned_processes(self):
        env = {**self.env, 'CLI_SLEEP': '60'}
        process = subprocess.Popen(self.command('app-server', '--stdio'), env=env)
        self.wait_for(self.root / 'cli.json')
        manager = int((self.root / 'manager.pid').read_text())
        cli = json.loads((self.root / 'cli.json').read_text())['pid']
        process.kill()
        process.wait(timeout=5)
        def alive(pid):
            try:
                os.kill(pid, 0)
                return True
            except ProcessLookupError:
                return False
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if not any(map(alive, (manager, cli))):
                break
            time.sleep(.02)
        for pid in (manager, cli):
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_explicit_host_is_forwarded_unchanged(self):
        subprocess.run(self.command('app-server', '--code-mode-host', 'http://127.0.0.1:7'), env=self.env, check=True, timeout=5)
        state = json.loads((self.root / 'cli.json').read_text())
        self.assertEqual(state['args'], ['app-server', '--code-mode-host', 'http://127.0.0.1:7'])
        self.assertFalse((self.root / 'manager.pid').exists())

    def test_killing_launcher_during_startup_cleans_manager(self):
        self.manager.write_text('import os,time\n'
                                'p=os.environ["MANAGER_STATE"];open(p+".tmp","w").write(str(os.getpid()));os.replace(p+".tmp",p)\n'
                                'time.sleep(60)\n')
        process = subprocess.Popen(self.command('app-server', '--stdio'), env=self.env)
        self.wait_for(self.root / 'manager.pid')
        manager = int((self.root / 'manager.pid').read_text())
        process.kill()
        process.wait(timeout=5)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                os.kill(manager, 0)
            except ProcessLookupError:
                break
            time.sleep(.02)
        with self.assertRaises(ProcessLookupError):
            os.kill(manager, 0)

    def test_stopped_server_is_not_mistaken_for_exit(self):
        process = subprocess.Popen(self.command('app-server', '--stdio'),
                                   env={**self.env, 'CLI_SLEEP': '1'})
        try:
            self.wait_for(self.root / 'cli.json')
            cli = json.loads((self.root / 'cli.json').read_text())['pid']
            os.kill(cli, signal.SIGSTOP)
            time.sleep(.2)
            self.assertIsNone(process.poll())
            os.kill(cli, signal.SIGCONT)
            self.assertEqual(process.wait(timeout=5), 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def test_http_proxy_preserves_native_execution_without_injection(self):
        result = subprocess.run(self.command('app-server', '--stdio'),
                                env={**self.env, 'HTTP_PROXY': 'http://127.0.0.1:1', 'CODEX_OPS_AUTO_OUTPUT': '1'},
                                capture_output=True, text=True, check=True, timeout=5)
        state = json.loads((self.root / 'cli.json').read_text())
        self.assertEqual(state['args'], ['app-server', '--stdio'])
        self.assertIsNone(state['env'])
        self.assertFalse((self.root / 'manager.pid').exists())
        self.assertIn('using native output', result.stderr)

    def test_failed_bridge_preserves_native_execution(self):
        self.manager.write_text('print("not an endpoint",flush=True)\n')
        result = subprocess.run(self.command('app-server', '--stdio'), env=self.env,
                                capture_output=True, text=True, check=True, timeout=15)
        state = json.loads((self.root / 'cli.json').read_text())
        self.assertEqual(state['args'], ['app-server', '--stdio'])
        self.assertIsNone(state['env'])
        self.assertIn('using native output', result.stderr)

    def test_permission_error_is_ignored_only_for_an_exited_leader(self):
        process = SimpleNamespace(pid=123)
        with patch.object(launcher_posix.os, 'killpg', side_effect=PermissionError), \
                patch.object(launcher_posix, '_exited', return_value=object()):
            launcher_posix._stop_group(process, signal.SIGTERM)
        with patch.object(launcher_posix.os, 'killpg', side_effect=PermissionError), \
                patch.object(launcher_posix, '_exited', return_value=None):
            with self.assertRaises(PermissionError):
                launcher_posix._stop_group(process, signal.SIGTERM)

    def test_cleanup_continues_after_one_group_cannot_be_signalled(self):
        first = SimpleNamespace(pid=11, wait=Mock(), stdout=None)
        second = SimpleNamespace(pid=22, wait=Mock(), stdout=None)
        with patch.object(launcher_posix, '_stop_group', side_effect=[PermissionError('blocked'), None, None, None]) as stop, \
                patch.object(launcher_posix.time, 'sleep'):
            failures = launcher_posix._cleanup([first, second])
        self.assertEqual(stop.call_count, 4)
        first.wait.assert_called_once_with(timeout=5)
        second.wait.assert_called_once_with(timeout=5)
        self.assertEqual(failures, ['blocked'])


if __name__ == '__main__':
    unittest.main()
