"""Windows file sharing must not take down a live Code Mode child after readiness."""
import copy
import ctypes
from ctypes import wintypes
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime_bridge'))
import manager
from native_cli import native_cli


def windows():
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                               wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    api.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    api.SetFileAttributesW.restype = wintypes.BOOL
    return api


class HeartbeatTests(unittest.TestCase):
    def test_real_shared_reader_preserves_live_thread_child_and_last_valid_json(self):
        with tempfile.TemporaryDirectory(prefix='codex-ops-heartbeat-') as folder:
            path = Path(folder) / 'status.json'
            relay = SimpleNamespace(lock=threading.Lock(), counts={'outboundFrames': 17})
            metadata = {'proof': 'EXACT_SOURCE_VALUE', 'nested': {'values': [1, 2, 3]}}
            original = copy.deepcopy(metadata)
            write = manager._status_writer(path, metadata, relay)
            write('ready')
            old = path.read_bytes()
            api = windows()
            handle = api.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x80, None)
            self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
            attempted, stop = threading.Event(), threading.Event()
            errors, sharing = [], []
            def observed(state):
                try:
                    write(state)
                except OSError as error:
                    sharing.append(error.winerror)
                    raise
                finally:
                    attempted.set()
            def heartbeat(native):
                try:
                    manager._heartbeat(native, stop, observed)
                except Exception as error:
                    errors.append(error)
            thread = None
            try:
                with manager._native_process(Path(native_cli()).with_name('codex-code-mode-host.exe')) as (native, address):
                    self.assertTrue(address.startswith('127.0.0.1:'))
                    thread = threading.Thread(target=heartbeat, args=(native,))
                    thread.start()
                    self.assertTrue(attempted.wait(4))
                    self.assertTrue(sharing and sharing[0] in (5, 32), sharing)
                    self.assertTrue(thread.is_alive())
                    self.assertIsNone(native.poll())
                    self.assertEqual(path.read_bytes(), old)
                    self.assertTrue(api.CloseHandle(handle))
                    handle = None
                    attempted.clear()
                    self.assertTrue(attempted.wait(4))
                    self.assertTrue(thread.is_alive())
                    self.assertIsNone(native.poll())
                    refreshed = json.loads(path.read_text())
                    self.assertEqual(refreshed['proof'], metadata['proof'])
                    self.assertEqual(refreshed['nested'], metadata['nested'])
                    self.assertEqual(refreshed['counters'], relay.counts)
                    self.assertNotEqual(path.read_bytes(), old)
                    self.assertEqual(metadata, original)
                    stop.set()
                    thread.join(4)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual(json.loads(path.read_text())['state'], 'stopped')
                    self.assertIsNone(native.poll())
                    self.assertEqual(errors, [])
            finally:
                stop.set()
                if handle is not None:
                    api.CloseHandle(handle)
                if thread is not None:
                    thread.join(4)

    def test_real_read_only_target_keeps_initial_handshake_strict_and_stopped_best_effort(self):
        with tempfile.TemporaryDirectory(prefix='codex-ops-heartbeat-readonly-') as folder:
            path = Path(folder) / 'status.json'
            manager.publish_status(path, {'state': 'ready', 'proof': 'PRESERVED'})
            before = path.read_bytes()
            api = windows()
            self.assertTrue(api.SetFileAttributesW(str(path), 1))
            try:
                relay = SimpleNamespace(lock=threading.Lock(), counts={})
                write = manager._status_writer(path, {}, relay)
                self.assertFalse(manager._try_heartbeat_write(write, 'ready'))
                self.assertFalse(manager._try_heartbeat_write(write, 'stopped'))
                with patch('manager._status_path', return_value=path), patch.dict(os.environ, {'CODEX_OPS_BRIDGE_SHIM_PID': '42'}):
                    output = io.StringIO()
                    with patch('sys.stdout', output), self.assertRaises(OSError) as failure:
                        manager._session(SimpleNamespace(pid=123), Path('native.exe'), 'hash', True,
                                         1, relay, 12345, threading.Event())
                    self.assertEqual(failure.exception.winerror, 5)
                    self.assertEqual(output.getvalue(), '')
                self.assertEqual(path.read_bytes(), before)
            finally:
                self.assertTrue(api.SetFileAttributesW(str(path), 0x80))
            self.assertTrue(manager._try_heartbeat_write(write, 'ready'))

    def test_unrelated_errors_and_native_child_exit_still_surface(self):
        for error in (OSError('unclassified'), RuntimeError('callback failure')):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)):
                    manager._try_heartbeat_write(lambda state: (_ for _ in ()).throw(error), 'ready')
        denied = OSError('unrelated Windows I/O')
        denied.winerror = 112
        with self.assertRaises(OSError):
            manager._try_heartbeat_write(lambda state: (_ for _ in ()).throw(denied), 'ready')
        stop = SimpleNamespace(wait=lambda seconds: False)
        native = SimpleNamespace(poll=lambda: 9)
        with self.assertRaisesRegex(RuntimeError, 'Native Code Mode host exited'):
            manager._heartbeat(native, stop, lambda state: self.fail('Exited native child cannot report ready'))


if __name__ == '__main__':
    unittest.main()
