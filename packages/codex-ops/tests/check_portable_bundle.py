"""Build a preview bundle, relocate it, install it and exercise its configured commands."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

import grpc
import owned_process

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_portable import build
from verify_portable_install import verify


def native_cli(archive, root, program='codex'):
    name = program + ('.exe' if os.name == 'nt' else '')
    if archive.is_dir():
        matches = list(archive.glob('openai-codex-0.165.0-alpha.1-*.tgz'))
        if len(matches) != 1:
            raise ValueError('Expected one pinned Codex archive')
        archive = matches[0]
    with tarfile.open(archive, 'r:gz') as package:
        entries = [entry for entry in package.getmembers() if entry.isfile() and entry.name.endswith('/bin/' + name)]
        if len(entries) != 1:
            raise ValueError('Expected one native Codex executable')
        executable = root / name
        with package.extractfile(entries[0]) as source, executable.open('wb') as target:
            shutil.copyfileobj(source, target)
    executable.chmod(0o755)
    return executable


def verify_relay(plugin, host, root, env):
    status_dir = root / 'bridge-status'
    status_dir.mkdir()
    shim = str(os.getpid())
    environment = {**env, 'CODEX_OPS_BRIDGE_STATUS': str(status_dir), 'CODEX_OPS_BRIDGE_SHIM_PID': shim}
    python = plugin / '.venv/bin/python'
    log = root / 'bridge-stderr.log'
    with log.open('wb') as errors:
        manager = subprocess.Popen([str(python), str(plugin / 'runtime_bridge/manager.py'), '--native-host', str(host)],
                                   env=environment, stdout=subprocess.DEVNULL, stderr=errors)
        try:
            status_path = status_dir / (shim + '.json')
            deadline = time.monotonic() + 15
            status = None
            while time.monotonic() < deadline and manager.poll() is None:
                if status_path.exists():
                    status = json.loads(status_path.read_text(encoding='utf-8'))
                    if status.get('state') == 'ready':
                        break
                time.sleep(0.05)
            if status is None or status.get('state') != 'ready':
                raise RuntimeError('Bridge manager failed to start: ' + log.read_text(encoding='utf-8'))
            if status['compressionEnabled']:
                raise AssertionError('An unvalidated host must forward unchanged')
            channel = grpc.insecure_channel(status['address'].removeprefix('http://'))
            try:
                grpc.channel_ready_future(channel).result(timeout=5)
                call = channel.stream_stream('/codex.PortableProbe/Unknown')
                try:
                    list(call(iter([b'probe']), timeout=5))
                except grpc.RpcError as error:
                    if error.code() != grpc.StatusCode.UNIMPLEMENTED:
                        raise
                else:
                    raise AssertionError('Native host unexpectedly accepted unknown method')
            finally:
                channel.close()
        finally:
            manager.terminate()
            manager.wait(timeout=10)
    if manager.returncode != 0:
        raise RuntimeError('Bridge manager did not stop cleanly: ' + log.read_text(encoding='utf-8'))
    if json.loads(status_path.read_text(encoding='utf-8'))['state'] != 'stopped':
        raise AssertionError('Bridge manager did not publish shutdown')
    print('Native host relay started, forwarded an RPC and stopped cleanly')


def main(output, archive=None):
    uv = shutil.which('uv')
    if not uv:
        raise RuntimeError('uv is required to build the bundle')
    bundle = build(output, uv)
    with tempfile.TemporaryDirectory(prefix='codex-ops-bundle-test-') as temporary:
        root = Path(temporary).resolve()
        relocated = root / 'relocated bundle'
        shutil.copytree(bundle, relocated)
        env = {key: value for key, value in os.environ.items()
               if key not in ('CODEX_OPS_WORKER', 'CODEX_OPS_KERNEL', 'UV_PROJECT_ENVIRONMENT')}
        install = (['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(relocated / 'install.ps1')]
                   if os.name == 'nt' else ['sh', str(relocated / 'install.sh')])
        owned_process.run(install, check=True, env=env)
        workspace = root / 'workspace'
        workspace.mkdir()
        (workspace / 'sample.txt').write_text('installed plugin evidence\n', encoding='utf-8')
        env.update({'CODEX_OPS_STORE': str(root / 'store'), 'PYTHONUTF8': '1'})
        asyncio.run(verify(relocated / 'plugin', workspace, env))
        if archive:
            codex = native_cli(archive, root)
            host = native_cli(archive, root, 'codex-code-mode-host')
            host_env = {**env, 'PATH': str(root) + os.pathsep + env.get('PATH', '')}
            owned_process.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(ROOT / 'tests'),
                               '-p', 'test_v06_workflow_sdk.py'], cwd=ROOT, env=host_env, check=True)
            if os.name != 'nt':
                verify_relay(relocated / 'plugin', host, root, env)
            home = root / 'codex-home'
            home.mkdir()
            # Codex can start a background curated-marketplace clone even during
            # plugin installation. Redirect that unrelated Git fetch in every
            # isolated Codex invocation, so its child cannot outlive the test home.
            offline_git = {'GIT_CONFIG_COUNT': '1',
                           'GIT_CONFIG_KEY_0': 'url.http://127.0.0.1:1/.insteadOf',
                           'GIT_CONFIG_VALUE_0': 'https://github.com/openai/plugins',
                           'GIT_TERMINAL_PROMPT': '0'}
            env.update({'CODEX_HOME': str(home), **offline_git})
            owned_process.run([str(codex), 'plugin', 'marketplace', 'add', str(relocated), '--json'],
                              env=env, check=True, capture_output=True, text=True)
            installed = owned_process.run([str(codex), 'plugin', 'add', 'codex-ops@codex-ops-portable', '--json'],
                                          env=env, check=True, capture_output=True, text=True)
            cached = Path(json.loads(installed.stdout)['installedPath'])
            asyncio.run(verify(cached, workspace, env))
            probe_env = {key: value for key, value in host_env.items()
                         if key.lower() not in ('http_proxy', 'https_proxy', 'all_proxy')}
            probe_env.update(offline_git)
            owned_process.run([sys.executable, str(ROOT / 'tests/probe_app_server.py'),
                               '--case', 'text', '--compress', '--require-pass', '--installed-home', str(home)],
                              cwd=ROOT, env=probe_env, check=True, timeout=90)
            print('Codex installed the plugin in an isolated home and its MCP and hook passed')
    print('Relocated bundle installation, MCP and SessionStart hook passed')


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
