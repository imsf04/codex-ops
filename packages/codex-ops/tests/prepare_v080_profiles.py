"""Build private native-plugin acceptance homes without changing the desktop profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from native_cli import native_cli, mcp_python
from host_rpc import call

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT.parent / 'codex-ops'
PRIVATE = Path(os.environ['LOCALAPPDATA']) / 'CodexOps' / 'acceptance-0.8'


def checked_extract(archive, destination):
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if not (destination / name).resolve().is_relative_to(destination.resolve()):
                raise ValueError('Archive member leaves baseline directory')
        bundle.extractall(destination)


def baseline(version, area):
    if version == '0.8.0':
        return ROOT
    target = area / 'source'
    if version == '0.6.1':
        checked_extract(LIVE / 'verification/source-0.6.1.zip', target)
    else:
        shutil.copytree(LIVE, target, ignore=shutil.ignore_patterns('.venv','__pycache__','verification','.coverage','*.pdb'))
    return target


def descriptor(source, area, observer):
    package = area / 'marketplace' / 'plugins' / 'codex-ops'
    package.mkdir(parents=True)
    for name in ('.codex-plugin', 'skills'):
        shutil.copytree(source / name, package / name)
    settings = json.loads((source / '.mcp.json').read_text())
    server = settings['mcpServers']['codex_ops']
    server['args'] = ['-u', str(observer), '--package', str(source)]
    server['env_vars'] = ['CODEX_OPS_STORE', 'CODEX_OPS_MEASUREMENT_ORIGIN']
    (package / '.mcp.json').write_text(json.dumps(settings, indent=2), encoding='utf-8')
    hooks = json.loads((source / 'hooks/hooks.json').read_text())
    for groups in hooks['hooks'].values():
        for group in groups:
            for hook in group['hooks']:
                command = '& "' + str(mcp_python()).replace('\\','/') + '" "' + str(source / 'hook.py').replace('\\','/') + '"'
                hook['command'] = command
                hook['commandWindows'] = command
    (package / 'hooks').mkdir()
    (package / 'hooks/hooks.json').write_text(json.dumps(hooks, indent=2), encoding='utf-8')
    return package


def native(command, environment):
    result = subprocess.run([native_cli(), *command], env=environment, cwd=PRIVATE,
                            capture_output=True, text=True, encoding='utf-8', timeout=60,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def trust_hooks(environment):
    result = call('hooks/list', {}, environment, str(PRIVATE))
    hooks = [h for group in result['result']['data'] for h in group['hooks'] if 'codex-ops' in json.dumps(h)]
    if len(hooks) != 2:
        raise ValueError('Expected exactly two acceptance plugin hooks')
    for hook in hooks:
        definition, content = hook['currentHash'].split('/')
        if not definition or not content:
            raise ValueError('Native hook trust hashes are absent')
        response = call('config/value/write', {'keyPath': 'hooks.state.' + json.dumps(hook['key']),
                        'mergeStrategy': 'upsert', 'value': {'trusted_hash': definition,
                        'trusted_content_hash': content}}, environment, str(PRIVATE))
        if 'error' in response:
            raise ValueError(response['error'])
    return call('hooks/list', {}, environment, str(PRIVATE))


def prepare(version, observer, resume=False):
    area = PRIVATE / version
    if resume:
        assert area.is_dir() and not (area / 'profile.json').exists()
        source = ROOT if version == '0.8.0' else area / 'source'
        return finish(version, observer, area, source)
    area.mkdir(parents=True, exist_ok=False)
    source = baseline(version, area)
    home = area / 'home'
    home.mkdir()
    shutil.copy2(Path.home() / '.codex/auth.json', home / 'auth.json')
    (home / 'config.toml').write_text('model = "gpt-6.1-terra"\nmodel_reasoning_effort = "medium"\n'
        'approval_policy = "never"\nsandbox_mode = "workspace-write"\n'
        '[windows]\nsandbox = "elevated"\n[features]\nplugins = true\n', encoding='utf-8')
    descriptor(source, area, observer)
    registry = area / 'marketplace' / '.agents' / 'plugins'
    registry.mkdir(parents=True)
    marketplace = 'codex-ops-acceptance-' + version.replace('.','')
    manifest = {'name': marketplace, 'interface': {'displayName': 'Codex Ops acceptance'},
        'plugins': [{'name': 'codex-ops', 'source': {'source': 'local', 'path': './plugins/codex-ops'},
                     'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'}, 'category': 'Productivity'}]}
    (registry / 'marketplace.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return finish(version, observer, area, source)


def finish(version, observer, area, source):
    home = area / 'home'
    marketplace = 'codex-ops-acceptance-' + version.replace('.','')
    environment = {**os.environ, 'CODEX_HOME': str(home)}
    registered = native(['plugin','marketplace','add',str(area / 'marketplace'),'--json'], environment)
    installed = native(['plugin','add','codex-ops@' + marketplace,'--json'], environment)
    hooks = trust_hooks(environment)
    own = [h for group in hooks['result']['data'] for h in group['hooks'] if 'codex-ops' in json.dumps(h)]
    assert len(own) == 2 and all(h['enabled'] and h['trustStatus'] == 'trusted' for h in own)
    (area / 'native-hooks.json').write_text(json.dumps(hooks, indent=2), encoding='utf-8')
    hashes = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source.rglob('*.py') if not any(part in ('.venv','__pycache__','verification','tests') for part in p.parts)}
    record = {'version': version, 'home': str(home), 'source': str(source), 'marketplace': marketplace,
              'hooksTrusted': len(own), 'observer': str(observer), 'sourceSha256': hashes,
              'registered': registered, 'installed': installed, 'auth': 'Private local auth copy; not part of repository or release package'}
    (area / 'profile.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    return {k:record[k] for k in ('version','home','source','hooksTrusted','observer')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('versions', nargs='+', choices=('0.6.1','0.7.0','0.8.0'))
    parser.add_argument('--observer', type=Path, required=True)
    parser.add_argument('--resume-setup', action='store_true')
    options = parser.parse_args()
    assert options.observer.is_file()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    for version in options.versions:
        print(json.dumps(prepare(version, options.observer.resolve(), options.resume_setup)), flush=True)
