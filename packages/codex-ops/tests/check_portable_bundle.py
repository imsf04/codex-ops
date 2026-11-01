"""Build a preview bundle, relocate it, install it and exercise its configured commands."""
import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_portable import build
from verify_portable_install import verify


def main(output):
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
    print('Relocated bundle installation, MCP and SessionStart hook passed')


if __name__ == '__main__':
    main(Path(sys.argv[1]))
