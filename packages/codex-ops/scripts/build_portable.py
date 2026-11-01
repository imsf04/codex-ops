"""Assemble a platform-specific plugin bundle from the current source and binaries."""
import argparse
import json
import os
from pathlib import Path
import shutil

SOURCE = Path(__file__).resolve().parents[1]
REPOSITORY = SOURCE.parents[1]


def build(destination, uv):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Bundle destination already exists')
    plugin = destination / 'plugin'
    plugin.mkdir(parents=True)
    for name in ('LICENSE', 'NOTICE'):
        shutil.copy2(REPOSITORY / name, destination / name)
    shutil.copytree(REPOSITORY / 'licenses', destination / 'licenses')
    for path in SOURCE.glob('*.py'):
        shutil.copy2(path, plugin / path.name)
    for name in ('.codex-plugin', 'hooks', 'skills', 'mutations', 'runtime_bridge', 'experimental', 'docs'):
        shutil.copytree(SOURCE / name, plugin / name,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'target', '.venv'))
    hooks_path = plugin / 'hooks' / 'hooks.json'
    hooks = json.loads(hooks_path.read_text(encoding='utf-8'))
    for groups in hooks['hooks'].values():
        for group in groups:
            for item in group['hooks']:
                item['command'] = 'echo Run the Codex Ops installer first'
                item.pop('commandWindows', None)
    hooks_path.write_text(json.dumps(hooks, indent=2) + '\n', encoding='utf-8')
    for name in ('pyproject.toml', 'uv.lock', 'LICENSE', 'README.md', 'README.zh-CN.md'):
        shutil.copy2(SOURCE / name, plugin / name)
    binary = plugin / 'bin'
    binary.mkdir()
    suffix = '.exe' if os.name == 'nt' else ''
    for name in ('dsh-ops-worker', 'codex-ops-kernel'):
        shutil.copy2(SOURCE / 'bin' / (name + suffix), binary / (name + suffix))
    shim = SOURCE / 'bin' / 'codex-ops-cli.exe'
    if os.name == 'nt':
        shutil.copy2(shim, binary / shim.name)
    shutil.copy2(uv, binary / ('uv' + suffix))
    marketplace = destination / '.agents' / 'plugins'
    marketplace.mkdir(parents=True)
    index = {'name': 'codex-ops-portable', 'interface': {'displayName': 'Codex Ops Portable'},
             'plugins': [{'name': 'codex-ops', 'source': {'source': 'local', 'path': './plugin'},
                          'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'},
                          'category': 'Productivity'}]}
    (marketplace / 'marketplace.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')
    for source, target in (('portable-package.md', 'INSTALL.md'),
                           ('portable-package.zh-CN.md', 'INSTALL.zh-CN.md')):
        shutil.copy2(SOURCE / 'docs' / source, destination / target)
    (destination / 'install.sh').write_text(
        '#!/bin/sh\nset -eu\nroot=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        'chmod +x "$root/plugin/bin/uv" "$root/plugin/bin/dsh-ops-worker" "$root/plugin/bin/codex-ops-kernel"\n'
        '"$root/plugin/bin/uv" sync --locked --no-dev --project "$root/plugin"\n'
        '"$root/plugin/.venv/bin/python" "$root/plugin/portable_install.py"\n', encoding='utf-8')
    (destination / 'install.ps1').write_text(
        '$ErrorActionPreference = "Stop"\n$root = $PSScriptRoot\n'
        '& "$root/plugin/bin/uv.exe" sync --locked --no-dev --project "$root/plugin"\n'
        'if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n'
        '& "$root/plugin/.venv/Scripts/python.exe" "$root/plugin/portable_install.py"\n'
        'exit $LASTEXITCODE\n', encoding='utf-8')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--uv', required=True, type=Path)
    args = parser.parse_args()
    print(build(args.output, args.uv))
