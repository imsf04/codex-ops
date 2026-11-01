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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_portable import build
from verify_portable_install import verify


def native_cli(archive, root):
    name = 'codex.exe' if os.name == 'nt' else 'codex'
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
        subprocess.run(install, check=True, env=env)
        workspace = root / 'workspace'
        workspace.mkdir()
        (workspace / 'sample.txt').write_text('installed plugin evidence\n', encoding='utf-8')
        env.update({'CODEX_OPS_STORE': str(root / 'store'), 'PYTHONUTF8': '1'})
        asyncio.run(verify(relocated / 'plugin', workspace, env))
        if archive:
            codex = native_cli(archive, root)
            home = root / 'codex-home'
            home.mkdir()
            env['CODEX_HOME'] = str(home)
            subprocess.run([str(codex), 'plugin', 'marketplace', 'add', str(relocated), '--json'],
                           env=env, check=True, capture_output=True, text=True)
            installed = subprocess.run([str(codex), 'plugin', 'add', 'codex-ops@codex-ops-portable', '--json'],
                                       env=env, check=True, capture_output=True, text=True)
            cached = Path(json.loads(installed.stdout)['installedPath'])
            asyncio.run(verify(cached, workspace, env))
            print('Codex installed the plugin in an isolated home and its MCP and hook passed')
    print('Relocated bundle installation, MCP and SessionStart hook passed')


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
