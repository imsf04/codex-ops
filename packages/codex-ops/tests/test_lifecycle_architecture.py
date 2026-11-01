"""Exercise installation and host lifetime through their existing interfaces."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime_bridge'))
if os.name == 'nt':
    import control
import manager


@unittest.skipUnless(os.name == 'nt', 'Windows registry and Desktop control')
class InstallationInterfaceTests(unittest.TestCase):
    def test_registry_write_delete_and_missing_delete_broadcast_without_other_keys(self):
        registry_key = MagicMock()
        broadcaster = MagicMock()
        with patch.object(control.winreg, 'OpenKey', return_value=registry_key) as opened, \
                patch.object(control.winreg, 'SetValueEx') as assign, \
                patch.object(control.winreg, 'DeleteValue') as delete, \
                patch.object(control.ctypes, 'WinDLL', return_value=broadcaster):
            value = {'value': '%USERPROFILE%/owned.exe', 'type': control.winreg.REG_EXPAND_SZ}
            control.write_environment(value)
            assign.assert_called_once_with(registry_key.__enter__(), control.NAME, 0, value['type'], value['value'])
            delete.assert_not_called()
            control.write_environment({'value': None})
            delete.assert_called_once_with(registry_key.__enter__(), control.NAME)
            delete.side_effect = FileNotFoundError()
            control.write_environment({'value': None})
            self.assertEqual(assign.call_count, 1)
            self.assertEqual(broadcaster.SendMessageTimeoutW.call_count, 3)
            self.assertEqual(broadcaster.SendMessageTimeoutW.call_args.args[:6],
                             (0xffff, 0x001A, 0, 'Environment', 0x0002, 2000))
            opened.assert_called_with(control.winreg.HKEY_CURRENT_USER, 'Environment', 0, control.winreg.KEY_SET_VALUE)

    def test_registry_reader_retains_value_type_and_distinguishes_missing(self):
        with patch.object(control.winreg, 'CreateKey', return_value=MagicMock()), \
                patch.object(control.winreg, 'QueryValueEx', return_value=('previous', control.winreg.REG_EXPAND_SZ)) as read:
            self.assertEqual(control.user_environment(), {'value': 'previous', 'type': control.winreg.REG_EXPAND_SZ})
            read.side_effect = FileNotFoundError()
            self.assertEqual(control.user_environment(), {'value': None, 'type': control.winreg.REG_SZ})

    def test_status_uses_fresh_live_instances_and_ignores_partial_or_invalid_records(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'bridge').mkdir()
            values = [{'pid': 11, 'updatedAt': 100, 'runtimeVersion': control.VERSION}, {'pid': 12, 'updatedAt': 100},
                      {'pid': 13, 'updatedAt': 90}, {}, {'updatedAt': None}]
            for index, value in enumerate(values):
                (root / 'bridge' / f'{index}.json').write_text(json.dumps(value))
            (root / 'bridge/partial.json').write_text('{')
            with patch.object(control, 'BASE', root), patch.object(control.time, 'time', return_value=101), \
                    patch.object(control, 'alive', side_effect=lambda pid: pid == 11) as live, \
                    patch.object(control, 'user_environment', return_value={'value': 'configured.exe'}), \
                    patch.object(control.runtime_status, 'current', return_value={'runtimeVersion': control.VERSION}):
                result = control.status()
            self.assertEqual(result['activeInstances'], [values[0]])
            self.assertFalse(result['restartRequired'])
            self.assertEqual(result['configuredOverride'], 'configured.exe')
            self.assertEqual([call.args[0] for call in live.call_args_list], [11, 12])

    def test_alive_tracks_owned_process_and_releases_handle_on_query_failure(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.assertTrue(control.alive(child.pid))
        finally:
            child.terminate()
            child.wait(timeout=5)
        self.assertFalse(control.alive(child.pid))
        self.assertFalse(control.alive(0))
        kernel = MagicMock()
        kernel.OpenProcess.return_value = 123
        kernel.GetExitCodeProcess.return_value = 0
        with patch.object(control.ctypes, 'WinDLL', return_value=kernel):
            self.assertFalse(control.alive(1234))
        kernel.CloseHandle.assert_called_once_with(123)

    def test_stage_rejects_wrong_version_missing_runtime_and_changed_alias(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            native = root / 'native.exe'
            native.write_bytes(b'native fixture')
            with patch.object(control, 'DESTINATION', root), \
                    patch.object(control, '_native_cli', return_value=native), \
                    patch.dict(os.environ, {'CODEX_OPS_BRIDGE_PYTHON': sys.executable}):
                with patch.object(control, 'VERSION', 'not-the-manifest'):
                    with self.assertRaisesRegex(ValueError, 'versions must match'):
                        control.stage()
                with patch.object(control, '_native_cli', return_value=root / 'missing.exe'):
                    with self.assertRaises(FileNotFoundError):
                        control.stage()
                with patch.dict(os.environ, {'CODEX_OPS_BRIDGE_PYTHON': str(root / 'missing-python.exe')}):
                    with self.assertRaises(FileNotFoundError):
                        control.stage()
                control.stage()
                (root / 'bin/codex.exe').write_bytes(b'changed alias')
                with self.assertRaisesRegex(ValueError, 'CLI alias differs'):
                    control.stage()

    def test_stage_resolves_registry_fallback_and_rejects_no_native_selector(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            native = root / 'native.exe'
            native.write_bytes(b'native fixture')
            with patch.object(control, 'DESTINATION', root / 'bundle'), \
                    patch.object(control.shutil, 'which', return_value=None), \
                    patch.dict(control.os.environ, {'CODEX_APP_RUNTIME_CLI_PATH': '',
                                                    'CODEX_OPS_BRIDGE_PYTHON': sys.executable}), \
                    patch.object(control, 'user_environment', return_value={'value': str(native)}) as environment:
                control.stage()
                self.assertEqual((root / 'bundle/bin/real-cli.txt').read_text().strip(), str(native))
                environment.return_value = {'value': None}
                with self.assertRaises(FileNotFoundError):
                    control.stage()

    def test_launch_resolves_unique_installation_and_sanitizes_inherited_bridge_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            desktop = root / 'package/app/ChatGPT.exe'
            desktop.parent.mkdir(parents=True)
            desktop.write_bytes(b'not executed')
            listing = f'\n{root / "missing"}\n  {root / "package"}  \n\n'
            values = {control.NAME: 'inherited.exe', 'CODEX_OPS_AUTO_OUTPUT': '1',
                      'CODEX_OPS_BRIDGE_MANAGER_PID': '7', 'CODEX_OPS_BRIDGE_SHIM_PID': '8',
                      'CRAP_LAUNCH_HOME': str(root), 'LIFECYCLE_KEEP': 'yes'}
            with patch.dict(control.os.environ, values), \
                    patch.object(control, 'user_environment', return_value={'value': '%CRAP_LAUNCH_HOME%/shim.exe'}) as environment, \
                    patch.object(control.subprocess, 'run', return_value=Mock(stdout=listing)), \
                    patch.object(control.subprocess, 'Popen', return_value=Mock(pid=123)) as spawn:
                result = control.launch()
                selected = spawn.call_args.kwargs['env']
                self.assertEqual(selected[control.NAME], str(root) + '/shim.exe')
                self.assertEqual(selected['LIFECYCLE_KEEP'], 'yes')
                self.assertFalse(any(key in selected for key in values if key.startswith('CODEX_OPS_')))
                self.assertEqual(result['desktop'], str(desktop))
                self.assertEqual(result['launchedPid'], 123)
                environment.return_value = {'value': None}
                control.launch()
                self.assertNotIn(control.NAME, spawn.call_args.kwargs['env'])
            self.assertEqual(os.environ.get('LIFECYCLE_KEEP'), None)

    def test_launch_rejects_zero_or_multiple_installations_before_spawning(self):
        with tempfile.TemporaryDirectory() as folder:
            roots = [Path(folder) / name for name in ('one', 'two')]
            for root in roots:
                (root / 'app').mkdir(parents=True)
                (root / 'app/ChatGPT.exe').touch()
            with patch.object(control.subprocess, 'run') as query, patch.object(control.subprocess, 'Popen') as spawn:
                for listing in ('', '\n'.join(map(str, roots))):
                    query.return_value = Mock(stdout=listing)
                    with self.assertRaisesRegex(RuntimeError, 'one installed'):
                        control.launch()
                query.side_effect = subprocess.CalledProcessError(1, ['powershell'])
                with self.assertRaises(subprocess.CalledProcessError):
                    control.launch()
                spawn.assert_not_called()


class ManagerLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.host = self.root / 'host.exe'
        self.host.write_bytes(b'unknown native host fixture')
        self.native = Mock(pid=42)
        self.native.stdout.readline.return_value = b'http://127.0.0.1:12345\n'
        self.native.poll.return_value = None
        self.server, self.channel = Mock(), Mock()
        self.relay = Mock(lock=threading.Lock(), counts={'compactedFrames': 2})
        self.stop = Mock()
        self.stop.wait.side_effect = [False, True]
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.dict(os.environ, {'CODEX_OPS_BRIDGE_SHIM_PID': '43', 'CODEX_OPS_BRIDGE_STATUS': str(self.root)}))
        self.stack.enter_context(patch.object(sys, 'argv', ['manager.py', '--native-host', str(self.host)]))
        self.stack.enter_context(patch.object(manager.subprocess, 'Popen', return_value=self.native))
        self.serve = self.stack.enter_context(patch.object(manager, 'serve', return_value=(self.server, self.channel, self.relay, 23456)))
        self.stack.enter_context(patch.object(manager, '_stop_event', return_value=self.stop))
        self.stdout, self.stderr = io.StringIO(), io.StringIO()
        self.stack.enter_context(contextlib.redirect_stdout(self.stdout))
        self.stack.enter_context(contextlib.redirect_stderr(self.stderr))

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    def test_unknown_host_forwards_without_compression_and_finishes_owned_resources(self):
        manager.main()
        self.serve.assert_called_once_with('127.0.0.1:12345', enabled=False)
        self.assertIn('forwarding output unchanged', self.stderr.getvalue())
        self.assertEqual(self.stdout.getvalue(), 'http://127.0.0.1:23456\n')
        status = json.loads((self.root / '43.json').read_text())
        self.assertEqual(status['state'], 'stopped')
        self.assertEqual(status['shimPid'], 43)
        self.assertEqual(status['nativeHostPid'], 42)
        self.assertEqual(status['nativeSha256'], hashlib.sha256(self.host.read_bytes()).hexdigest())
        self.assertEqual(status['counters'], {'compactedFrames': 2})
        self.server.stop.assert_called_once_with(0)
        self.channel.close.assert_called_once_with()
        self.native.terminate.assert_called_once_with()
        self.native.wait.assert_called_once_with(timeout=5)

    def test_validated_host_enables_compression_without_warning(self):
        with patch.object(manager, '_configuration', return_value=(self.host, 'validated-digest', True)):
            manager.main()
        self.serve.assert_called_once_with('127.0.0.1:12345', enabled=True)
        self.assertEqual(self.stderr.getvalue(), '')

    def test_host_exit_keeps_failure_and_closes_relay_without_second_termination(self):
        self.native.poll.return_value = 7
        with self.assertRaisesRegex(RuntimeError, 'host exited'):
            manager.main()
        self.native.terminate.assert_not_called()
        self.native.wait.assert_called_once_with(timeout=5)
        self.server.stop.assert_called_once_with(0)
        self.channel.close.assert_called_once_with()

    def test_invalid_native_address_is_cleaned_up_before_any_relay_starts(self):
        self.native.stdout.readline.return_value = b'http://remote.example:1234\n'
        with self.assertRaisesRegex(RuntimeError, 'loopback'):
            manager.main()
        self.serve.assert_not_called()
        self.native.terminate.assert_called_once_with()
        self.native.wait.assert_called_once_with(timeout=5)

    def test_relay_start_failure_still_cleans_up_native_host(self):
        self.serve.side_effect = RuntimeError('relay unavailable')
        with self.assertRaisesRegex(RuntimeError, 'relay unavailable'):
            manager.main()
        self.native.terminate.assert_called_once_with()
        self.native.wait.assert_called_once_with(timeout=5)

    def test_missing_binary_fails_before_starting_any_process(self):
        self.host.unlink()
        with self.assertRaises(FileNotFoundError):
            manager.main()
        manager.subprocess.Popen.assert_not_called()

    def test_signals_request_normal_stop(self):
        # Bypass the fixture's stop-event replacement, but never replace OS handlers.
        self.stack.close()
        with patch.object(manager.signal, 'signal') as register:
            stop = manager._stop_event()
        self.assertEqual([call.args[0] for call in register.call_args_list], [manager.signal.SIGINT, manager.signal.SIGTERM])
        self.assertFalse(stop.is_set())
        register.call_args.args[1](manager.signal.SIGTERM, None)
        self.assertTrue(stop.is_set())


if __name__ == '__main__':
    unittest.main()
