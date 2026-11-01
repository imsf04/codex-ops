"""Windows integration tests; every process belongs to a disposable fake CLI tree."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
CREATE_NO_WINDOW = 0x08000000


def alive(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        status = ctypes.c_ulong()
        return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(status))) and status.value == 259
    finally:
        kernel.CloseHandle(handle)


CLI_SCRIPT = r'''
import json, os, subprocess, sys, time
from pathlib import Path
root = Path(os.environ['SHIM_TEST_STATE'])
(root / 'cli.pid').write_text(str(os.getpid()))
if os.environ.get('SHIM_TEST_HOLD'):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], creationflags=0x08000000)
    (root / 'cli-child.pid').write_text(str(child.pid))
    time.sleep(120)
else:
    print(json.dumps(dict(args=sys.argv[1:], cwd=os.getcwd(), value=os.environ.get('SHIM_TEST_VALUE'), auto=os.environ.get('CODEX_OPS_AUTO_OUTPUT'), manager_pid=os.environ.get('CODEX_OPS_BRIDGE_MANAGER_PID'), shim_pid=os.environ.get('CODEX_OPS_BRIDGE_SHIM_PID'), stdin=sys.stdin.read()), ensure_ascii=True), flush=True)
    print('native stderr', file=sys.stderr, flush=True)
    sys.exit(int(os.environ.get('SHIM_TEST_EXIT', '0')))
'''

MANAGER_SCRIPT = r'''
import json, os, subprocess, sys, time
from pathlib import Path
root = Path(os.environ['SHIM_TEST_STATE'])
(root / 'manager.pid').write_text(str(os.getpid()))
(root / 'manager-args.json').write_text(json.dumps(sys.argv[1:]))
(root / 'manager-shim.json').write_text(json.dumps(dict(parent=os.getppid(), declared=os.environ.get('CODEX_OPS_BRIDGE_SHIM_PID'))))
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], creationflags=0x08000000)
(root / 'manager-child.pid').write_text(str(child.pid))
mode = os.environ.get('SHIM_TEST_MANAGER')
if mode == 'exit': sys.exit(3)
if mode == 'timeout': time.sleep(120)
print('invalid endpoint' if mode == 'invalid' else 'http://127.0.0.1:54321', flush=True)
time.sleep(120)
'''


@unittest.skipUnless(os.name == 'nt' and shutil.which('rustc'), 'Windows and rustc required')
class ShimIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_tmp = tempfile.TemporaryDirectory(prefix='codex-ops-shim-build-')
        cls.build = Path(cls.build_tmp.name)
        cls.shim_build = cls.build / 'shim.exe'
        subprocess.run(['rustc', '--edition', '2024', '-O', str(ROOT / 'runtime_bridge/shim.rs'), '-o', str(cls.shim_build)], check=True, capture_output=True)
        # A real EXE trampoline exercises Windows argv quoting and native child inheritance.
        source = cls.build / 'fake.rs'
        source.write_text('use std::process::Command; fn main() { let s = Command::new(r#"' + sys.executable + '"#).arg(std::env::var_os("SHIM_TEST_SCRIPT").unwrap()).args(std::env::args_os().skip(1)).status().unwrap(); std::process::exit(s.code().unwrap_or(1)); }', encoding='utf-8')
        cls.fake_build = cls.build / 'fake.exe'
        subprocess.run(['rustc', '--edition', '2024', '-O', str(source), '-o', str(cls.fake_build)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.build_tmp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='codex-ops-shim-测试-')
        self.base = Path(self.tmp.name)
        self.bin = self.base / 'shim bin'
        self.bin.mkdir()
        self.native_dir = self.base / 'native bin'
        self.native_dir.mkdir()
        self.shim = self.bin / 'codex-ops-cli.exe'
        self.native = self.native_dir / 'codex.exe'
        shutil.copy2(self.shim_build, self.shim)
        shutil.copy2(self.fake_build, self.native)
        (self.native_dir / 'codex-code-mode-host.exe').touch()
        self.script = self.base / 'fake_cli.py'
        self.script.write_text(CLI_SCRIPT, encoding='utf-8')
        self.manager = self.base / 'fake_manager.py'
        self.manager.write_text(MANAGER_SCRIPT, encoding='utf-8')
        for name, value in [('real-cli.txt', self.native), ('bridge-python.txt', sys.executable), ('bridge-script.txt', self.manager)]:
            (self.bin / name).write_text(str(value), encoding='utf-8')
        self.env = dict(os.environ, SHIM_TEST_SCRIPT=str(self.script), SHIM_TEST_STATE=str(self.base), SHIM_TEST_VALUE='preserved 中文')
        self.env.pop('CODEX_OPS_AUTO_OUTPUT', None)
        self.env.pop('CODEX_OPS_BRIDGE_MANAGER_PID', None)
        self.env.pop('CODEX_OPS_BRIDGE_SHIM_PID', None)
        self.owned = []

    def tearDown(self):
        for proc in self.owned:
            if proc.poll() is None:
                proc.kill()
            proc.communicate(timeout=5)
        self.assert_stopped()
        self.tmp.cleanup()

    def assert_stopped(self):
        pids = [int(p.read_text()) for p in self.base.glob('*.pid')]
        deadline = time.monotonic() + 5
        while any(alive(pid) for pid in pids) and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertFalse([pid for pid in pids if alive(pid)], 'owned descendants survived shim exit')

    def run_cli(self, args, input='input 中文\n', **env):
        command = [str(self.shim), *args]
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', cwd=self.base, env=dict(self.env, **env), creationflags=CREATE_NO_WINDOW) as proc:
            try:
                stdout, stderr = proc.communicate(input, timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise
            result = subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)
            result.shim_pid = proc.pid
        return result, json.loads(result.stdout) if result.stdout else None

    def test_passthrough_quotes_unicode_stdio_environment_exit(self):
        args = ['exec', 'space and 中文', 'embedded"quote', 'trailing\\', '', '$HOME', '`literal`']
        result, data = self.run_cli(args, SHIM_TEST_EXIT='7', CODEX_OPS_BRIDGE_MANAGER_PID='preserve-non-service', CODEX_OPS_BRIDGE_SHIM_PID='preserve-non-service', CODEX_OPS_AUTO_OUTPUT='preserve-non-service')
        self.assertEqual(result.returncode, 7)
        self.assertEqual(data['args'], args)
        self.assertEqual(data['stdin'], 'input 中文\n')
        self.assertEqual(data['value'], 'preserved 中文')
        self.assertEqual(Path(data['cwd']), self.base)
        self.assertEqual(result.stderr.strip(), 'native stderr')
        self.assertEqual(data['manager_pid'], 'preserve-non-service')
        self.assertEqual(data['shim_pid'], 'preserve-non-service')
        self.assertEqual(data['auto'], 'preserve-non-service')
        self.assertFalse((self.base / 'manager.pid').exists())

    def test_non_service_modes_never_start_manager(self):
        modes = [['--version'], ['app-server', '--help'], ['app-server', 'daemon'], ['app-server', 'proxy'], ['app-server', 'generate-ts'], ['app-server', 'generate-json-schema'], ['app-server', '--print-startup-config'], ['-c', 'app-server', 'exec', 'ok']]
        for args in modes:
            with self.subTest(args=args):
                result, data = self.run_cli(args)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(data['args'], args)
                self.assertFalse((self.base / 'manager.pid').exists())

    def test_service_injects_endpoint_and_cleans_manager(self):
        args = ['-c', 'features.code_mode_host=true', 'app-server', '--analytics-default-enabled', '-c', 'key="quoted value"']
        result, data = self.run_cli(args)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(data['args'], args[:3] + ['--code-mode-host', 'http://127.0.0.1:54321'] + args[3:])
        self.assertEqual(data['auto'], '1')
        manager_identity = json.loads((self.base / 'manager-shim.json').read_text())
        self.assertIn(int(data['manager_pid']), [int((self.base / 'manager.pid').read_text()), manager_identity['parent']])
        self.assertEqual(data['shim_pid'], manager_identity['declared'])
        self.assertEqual(int(data['shim_pid']), result.shim_pid)
        self.assertEqual(json.loads((self.base / 'manager-args.json').read_text()), ['--native-host', str(self.native_dir / 'codex-code-mode-host.exe')])
        self.assert_stopped()

    def test_explicit_host_is_not_duplicated(self):
        for flag in [['--code-mode-host', 'http://localhost:1234'], ['--code-mode-host=http://localhost:1234']]:
            with self.subTest(flag=flag):
                args = ['app-server', *flag]
                result, data = self.run_cli(args)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(data['args'], args)
                self.assertFalse((self.base / 'manager.pid').exists())

    def test_bridge_failure_falls_back_with_owned_cleanup(self):
        for mode in ['invalid', 'exit', 'timeout']:
            with self.subTest(mode=mode):
                result, data = self.run_cli(['app-server'], SHIM_TEST_MANAGER=mode, CODEX_OPS_AUTO_OUTPUT='stale', CODEX_OPS_BRIDGE_MANAGER_PID='stale', CODEX_OPS_BRIDGE_SHIM_PID='stale')
                self.assertEqual(result.returncode, 0)
                self.assertEqual(data['args'], ['app-server'])
                self.assertIsNone(data['auto'])
                self.assertIsNone(data['manager_pid'])
                self.assertIsNone(data['shim_pid'])
                self.assertIn('using native output', result.stderr)
                self.assert_stopped()

    def test_missing_manager_falls_back(self):
        (self.bin / 'bridge-script.txt').unlink()
        result, data = self.run_cli(['app-server'])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(data['args'], ['app-server'])
        self.assertIn('bridge manager is unavailable', result.stderr)

    def test_job_assignment_failure_cleans_suspended_child(self):
        unit_binary = self.base / 'shim-unit.exe'
        subprocess.run(['rustc', '--edition', '2024', '--test', str(ROOT / 'runtime_bridge/shim.rs'), '-o', str(unit_binary)], check=True, capture_output=True)
        result = subprocess.run([str(unit_binary)], capture_output=True, text=True, timeout=10, creationflags=CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('1 passed', result.stdout)

    def test_bridge_process_creation_failure_falls_back(self):
        invalid_exe = self.base / 'not-an-executable.exe'
        invalid_exe.write_text('invalid executable')
        (self.bin / 'bridge-python.txt').write_text(str(invalid_exe), encoding='utf-8')
        result, data = self.run_cli(['app-server'])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(data['args'], ['app-server'])
        self.assertIn('bridge process could not start', result.stderr)

    def test_force_kill_shim_cleans_entire_owned_tree(self):
        proc = subprocess.Popen([str(self.shim), 'app-server'], cwd=self.base, env=dict(self.env, SHIM_TEST_HOLD='1'), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
        self.owned.append(proc)
        deadline = time.monotonic() + 10
        names = ['manager.pid', 'manager-child.pid', 'cli.pid', 'cli-child.pid']
        while not all((self.base / name).exists() for name in names) and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertTrue(all((self.base / name).exists() for name in names), 'fixture startup failed')
        self.assertTrue(all(alive(int((self.base / name).read_text())) for name in names))
        manager_identity = json.loads((self.base / 'manager-shim.json').read_text())
        self.assertEqual(int(manager_identity['declared']), proc.pid)
        proc.kill()  # Terminate only the shim, like Desktop ChildProcess.kill().
        proc.communicate(timeout=5)
        self.assert_stopped()

    def test_stale_cli_path_falls_back_to_path(self):
        (self.bin / 'real-cli.txt').write_text(str(self.base / 'missing.exe'))
        result, data = self.run_cli(['--version'], PATH=str(self.native_dir))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(data['args'], ['--version'])

    def test_cache_fallback_skips_self_and_chooses_newest(self):
        (self.bin / 'real-cli.txt').unlink()
        self.shim.rename(self.bin / 'codex.exe')
        self.shim = self.bin / 'codex.exe'
        cache = self.base / 'local/OpenAI/Codex/bin'
        for version, timestamp in [('old', 1_600_000_000), ('new', 1_700_000_000)]:
            directory = cache / version
            directory.mkdir(parents=True)
            shutil.copy2(self.fake_build, directory / 'codex.exe')
            os.utime(directory / 'codex.exe', (timestamp, timestamp))
            (directory / 'codex-code-mode-host.exe').touch()
        result, data = self.run_cli(['app-server'], PATH=str(self.bin), LOCALAPPDATA=str(self.base / 'local'))
        self.assertEqual(result.returncode, 0)
        manager_args = json.loads((self.base / 'manager-args.json').read_text())
        self.assertEqual(Path(manager_args[1]), cache / 'new/codex-code-mode-host.exe')
        self.assertEqual(data['auto'], '1')


if __name__ == '__main__':
    unittest.main()
