"""Install/inspect/revert the supported Desktop CLI override for this Windows user."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import winreg
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_status

VERSION = '0.8.0'
BASE = Path(os.environ['LOCALAPPDATA']) / 'CodexOps'
DESTINATION = BASE / 'runtime' / VERSION
NAME = 'CODEX_CLI_PATH'
FILES = ['runtime_bridge/manager.py', 'runtime_bridge/grpc_relay.py', 'runtime_bridge/projection.py',
         'runtime_bridge/wire.py', 'runtime_bridge/validated-host.json', 'pyproject.toml', 'uv.lock',
         'runtime_bridge/control.py', 'experimental/presentation.py', 'store.py', 'reducers.py',
         'structured.py', 'telemetry.py', 'progress.py', 'presentation_policy.py',
         'telemetry_details.py', 'bridge_context.py', 'frame_dedup.py', 'record_preview.py', 'retrieval_views.py',
         'semantic_preview.py', 'telemetry_windows.py', 'query_aggregates.py',
         'session_scope.py', 'runtime_status.py', 'evidence_preview.py', 'output_budget.py', 'workflow_inline.py',
         'workflow_view.py', 'diagnostic_view.py', 'log_contract.py', 'document_view.py', 'evidence_selection.py', 'native_observation_view.py',
         'delivery_metrics.py', 'cost_events.py', 'bin/codex-ops-cli.exe']


def user_environment():
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
        try:
            value, kind = winreg.QueryValueEx(key, NAME)
            return {'value': value, 'type': kind}
        except FileNotFoundError:
            return {'value': None, 'type': winreg.REG_SZ}


def write_environment(value):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_SET_VALUE) as key:
        if value['value'] is None:
            try:
                winreg.DeleteValue(key, NAME)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(key, NAME, 0, value['type'], value['value'])
    broadcast = ctypes.WinDLL('user32', use_last_error=True).SendMessageTimeoutW
    broadcast.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR,
                          wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
    broadcast.restype = ctypes.c_ssize_t
    result = ctypes.c_size_t()
    broadcast(0xffff, 0x001A, 0, 'Environment', 0x0002, 2000, ctypes.byref(result))


def alive(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    code = wintypes.DWORD()
    try:
        return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        kernel.CloseHandle(handle)


def status():
    observations = (_active_instance(path) for path in (BASE / 'bridge').glob('*.json'))
    active = [value for value in observations if value is not None]
    current = runtime_status.current()
    return {'configuredOverride': user_environment()['value'], 'version': VERSION,
            'activeInstances': active, 'currentProcess': current,
            'restartRequired': current.get('runtimeVersion') != VERSION}


def _active_instance(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if time.time() - value['updatedAt'] <= 5 and alive(value['pid']):
            return value
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _native_cli():
    selected = shutil.which('codex') or os.environ.get('CODEX_APP_RUNTIME_CLI_PATH') or user_environment()['value']
    real = Path(selected or '')
    adjacent = real.parent / 'real-cli.txt'
    if adjacent.is_file():
        real = Path(adjacent.read_text(encoding='utf-8').strip())
    return real


def _runtime_settings():
    python = Path.home() / '.local/share/codex-runtimes/codex-ops-uv/Scripts/python.exe'
    real = _native_cli()
    if not python.is_file() or not real.is_file():
        raise FileNotFoundError('The tested Python runtime and native CLI must exist')
    return {'real-cli.txt': str(real), 'bridge-python.txt': str(python),
            'bridge-script.txt': str(DESTINATION / 'runtime_bridge/manager.py')}


def _write_immutable(target, raw, message):
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError(message)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _stage_payloads(source):
    hashes = {}
    for name in FILES:
        raw = (source / name).read_bytes()
        hashes[name] = _write_immutable(DESTINATION / name, raw,
            'Versioned runtime already differs; bump the version before replacing it')
    # Desktop prepends the override's directory to shell PATH. Preserve the usual
    # `codex` command as well as the explicitly selected shim executable name.
    raw = (DESTINATION / 'bin/codex-ops-cli.exe').read_bytes()
    hashes['bin/codex.exe'] = _write_immutable(DESTINATION / 'bin/codex.exe', raw,
        'Versioned CLI alias differs; bump the version')
    return hashes


def stage():
    source = Path(__file__).resolve().parents[1]
    manifest = json.loads((source / '.codex-plugin/plugin.json').read_text(encoding='utf-8'))
    if manifest['version'] != VERSION:
        raise ValueError('Installer and plugin versions must match')
    settings = _runtime_settings()
    hashes = _stage_payloads(source)
    for name, value in settings.items():
        (DESTINATION / 'bin' / name).write_text(value + '\n', encoding='utf-8')
    receipt = {'version': VERSION, 'stagedAt': time.time(), 'files': hashes, 'settings': settings}
    (DESTINATION / 'bundle.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return {'staged': str(DESTINATION), 'files': len(hashes), 'override': str(DESTINATION / 'bin/codex-ops-cli.exe')}


def enable():
    receipt = json.loads((DESTINATION / 'bundle.json').read_text(encoding='utf-8'))
    for name, expected in receipt['files'].items():
        if hashlib.sha256((DESTINATION / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Staged runtime changed after validation: ' + name)
    override = str(DESTINATION / 'bin/codex-ops-cli.exe')
    backup = DESTINATION / 'environment-before.json'
    if not backup.exists():
        backup.write_text(json.dumps(user_environment(), indent=2), encoding='utf-8')
    write_environment({'value': override, 'type': winreg.REG_SZ})
    return status()


def rollback():
    current = user_environment()['value']
    expected = str(DESTINATION / 'bin/codex-ops-cli.exe')
    if current != expected:
        raise ValueError('Desktop override was changed separately; refusing to overwrite it')
    write_environment(json.loads((DESTINATION / 'environment-before.json').read_text(encoding='utf-8')))
    return {'restored': True, 'restartRequired': True, 'runtimeFilesRetained': str(DESTINATION)}


def _desktop_installations(output):
    paths = [Path(line.strip()) / 'app/ChatGPT.exe' for line in output.splitlines() if line.strip()]
    return [path for path in paths if path.is_file()]


def _desktop_executable():
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', '(Get-AppxPackage -Name OpenAI.Codex).InstallLocation'],
                            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
    installed = _desktop_installations(result.stdout)
    if len(installed) != 1:
        raise RuntimeError('Could not resolve one installed Codex Desktop')
    return installed[0]


def _launch_environment(selected):
    environment = dict(os.environ)
    if selected:
        environment[NAME] = os.path.expandvars(selected)
    else:
        environment.pop(NAME, None)
    environment.pop('CODEX_OPS_AUTO_OUTPUT', None)
    environment.pop('CODEX_OPS_BRIDGE_MANAGER_PID', None)
    environment.pop('CODEX_OPS_BRIDGE_SHIM_PID', None)
    return environment


def launch():
    desktop = _desktop_executable()
    selected = user_environment()['value']
    process = subprocess.Popen([str(desktop)], env=_launch_environment(selected), creationflags=subprocess.CREATE_NO_WINDOW)
    return {'launchedPid': process.pid, 'desktop': str(desktop), 'override': selected,
            'note': 'An already running Desktop keeps its original environment; fully quit before relaunch.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['stage', 'enable', 'status', 'rollback', 'launch'])
    args = parser.parse_args()
    print(json.dumps(globals()[args.action](), ensure_ascii=False, indent=2))
