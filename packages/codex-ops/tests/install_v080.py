"""Check or promote the accepted personal plugin; installation is explicit."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import winreg
import zipfile

from host_rpc import call
from native_cli import native_cli
from release_v080 import VERSION, digest, read, require, validate, verify_files

SOURCE = Path(__file__).resolve().parents[1]
LIVE = SOURCE.parent / 'codex-ops'
PREVIOUS = '0.7.0'
HOME = Path.home()
MARKETPLACE = HOME / '.agents/plugins/marketplace.json'
CONFIG = HOME / '.codex/config.toml'
PYTHON = HOME / '.local/share/codex-runtimes/codex-ops-uv/Scripts/python.exe'
SKIP = {'.venv', '__pycache__', '.git', 'verification', 'target'}
RECEIPTS = ('quality/crap.json', 'quality/crap.md', 'quality/coverage.json', 'rust-quality/latest.json',
            'v080-cost-summary.json', 'v080-native-final-summary.json', 'v080-native-final-current.json',
            'v080-native-friction-current.json', 'v080-runtime-friction-restage.json',
            'v080-runtime-final-restage.json', 'v080-cost-summary-frozen.json',
            'v080-experimental-acceptance.json', 'v080-kernel-build.json',
            'v080-desktop-sandbox-restored.json', 'plugin-package-0.8.0.json')


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def source_files(root):
    for directory, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if name not in SKIP]
        for name in names:
            if name.startswith('.coverage') and name != '.coveragerc':
                continue
            yield Path(directory) / name


def selector():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
        value, kind = winreg.QueryValueEx(key, 'CODEX_CLI_PATH')
    return {'value': value, 'type': kind}


def _python_health():
    code = ('import json,sys,sqlite3,importlib.metadata as m; '
            'db=sqlite3.connect(":memory:"); db.execute("CREATE VIRTUAL TABLE evidence USING fts5(text)"); '
            'print(json.dumps({"python":".".join(map(str,sys.version_info[:3])), '
            '"mcp":m.version("mcp"),"grpcio":m.version("grpcio"),"fts5":True}))')
    result = subprocess.run([str(PYTHON), '-c', code], capture_output=True, text=True, check=True)
    health = json.loads(result.stdout)
    require(health['python'] == (SOURCE / '.python-version').read_text().strip(), 'Production Python differs')
    require(health['mcp'] == '2.3.0' and health['grpcio'] == '1.76.0', 'Production uv dependencies differ')
    return health


def preflight():
    accepted = validate(SOURCE)
    require(read(LIVE / '.codex-plugin/plugin.json')['version'] == PREVIOUS, 'Live version changed independently')
    previous_quality = read(LIVE / 'verification/quality/crap.json')
    verify_files(LIVE, previous_quality['sourceSha256'])
    package = read(SOURCE / 'verification/plugin-package-0.8.0.json')
    expected = SOURCE.parent / 'codex-ops-plugin' / VERSION
    require(Path(package['package']).resolve() == expected.resolve(), 'Unexpected descriptor source')
    verify_files(expected, package['files'])
    manifest = read(SOURCE / '.mcp.json')['mcpServers']['codex_ops']
    require(Path(manifest['command']).resolve() == PYTHON.resolve(), 'Dedicated production uv is required')
    require(str(LIVE / 'server.py').replace('\\', '/') in manifest['args'], 'Descriptor must point to live source')
    selected = selector()
    require(Path(selected['value']).parents[1].name == PREVIOUS, 'Runtime selector changed independently')
    return {**accepted, 'package': package, 'previousQuality': previous_quality,
            'previousSelector': selected, 'productionPython': _python_health()}


def _checkpoint(stage, **fields):
    write(LIVE / 'verification/install-progress-0.8.0.json', {'stage': stage, 'at': time.time(), **fields})


def backup(state):
    folder = LIVE / 'verification'
    archive = folder / 'source-0.7.0.zip'
    receipts = folder / 'releases/0.7.0'
    saved = [archive, receipts, folder / 'marketplace-before-0.8.0.json', folder / 'config-before-0.8.0.toml']
    require(not any(path.exists() for path in saved), 'A previous promotion backup exists; inspect its checkpoint before retrying')
    files = list(source_files(LIVE))
    hashes = {path.relative_to(LIVE).as_posix(): digest(path) for path in files}
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as output:
        for path in files:
            output.write(path, path.relative_to(LIVE).as_posix())
    receipts.mkdir(parents=True)
    for name in ('desktop-installation.json', 'desktop-live-0.7.0.json', 'quality/crap.json', 'quality/coverage.json'):
        target = receipts / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(folder / name, target)
    shutil.copy2(MARKETPLACE, saved[2])
    shutil.copy2(CONFIG, saved[3])
    record = {'previousVersion': PREVIOUS, 'archive': str(archive), 'archiveSha256': digest(archive),
              'files': hashes, 'selector': state['previousSelector'], 'marketplace': str(saved[2]),
              'config': str(saved[3]), 'receipts': str(receipts),
              'runtimeRetained': str(Path(state['previousSelector']['value']).parents[1])}
    write(folder / 'rollback-0.8.0.json', record)
    _checkpoint('backed-up', backup=str(archive))
    return record


def promote(state, previous):
    copied = []
    for path in source_files(SOURCE):
        relative = path.relative_to(SOURCE)
        target = LIVE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(relative.as_posix())
    for name in RECEIPTS:
        target = LIVE / 'verification' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / 'verification' / name, target)
    verify_files(LIVE, state['condition']['sourceSha256'])
    verify_files(LIVE, state['costs']['binarySha256'])
    previous['newFiles'] = sorted(set(copied) - set(previous['files']))
    write(LIVE / 'verification/rollback-0.8.0.json', previous)
    _checkpoint('source-promoted', rustBinary=state['costs']['binarySha256']['bin/codex-ops-kernel.exe'])


def native_environment():
    return {**os.environ, 'CODEX_HOME': str(HOME / '.codex')}


def install_descriptor(state):
    registry = read(MARKETPLACE)
    entries = [entry for entry in registry['plugins'] if entry['name'] == 'codex-ops']
    require(len(entries) == 1, 'Expected one personal codex-ops marketplace entry')
    entries[0]['source']['path'] = './code/dsh-ops/packages/codex-ops-plugin/0.8.0'
    write(MARKETPLACE, registry)
    subprocess.run([native_cli(), 'plugin', 'add', 'codex-ops@personal', '--json'],
                   env=native_environment(), cwd=LIVE, check=True)
    installed = HOME / '.codex/plugins/cache/personal/codex-ops/0.8.0'
    verify_files(installed, state['package']['files'])
    _checkpoint('native-package-installed', package=str(installed))
    return installed


def _hooks():
    result = call('hooks/list', {}, env=native_environment(), cwd=str(LIVE))
    require('error' not in result, 'Native hooks/list failed')
    hooks = [hook for group in result['result']['data'] for hook in group['hooks']
             if hook.get('pluginId') == 'codex-ops@personal']
    require({hook['eventName'] for hook in hooks} == {'sessionStart', 'postToolUse'} and len(hooks) == 2,
            'Unexpected installed hook set')
    return result, hooks


def trust_hooks(installed):
    _, hooks = _hooks()
    expected = installed / 'hooks/hooks.json'
    for hook in hooks:
        require(Path(hook['sourcePath']).resolve() == expected.resolve(), 'Unexpected hook source')
        require(hook['enabled'] and not hook['isManaged'], 'Installed hook is disabled or managed')
        definition, contents = hook['currentHash'].split('/')
        result = call('config/value/write', {'keyPath': 'hooks.state.' + json.dumps(hook['key']),
                      'mergeStrategy': 'upsert', 'value': {'trusted_hash': definition, 'trusted_content_hash': contents}},
                      env=native_environment(), cwd=str(LIVE))
        require('error' not in result, 'Native hook trust write failed')
    result, hooks = _hooks()
    require(all(hook['enabled'] and hook['trustStatus'] == 'trusted' for hook in hooks), 'Native hook trust readback failed')
    write(LIVE / 'verification/native-hooks-0.8.0.json', result)
    _checkpoint('native-hooks-trusted', hooks=len(hooks))


def enable(state, installed, previous):
    control = state['runtime'] / 'runtime_bridge/control.py'
    result = subprocess.run([str(PYTHON), str(control), 'enable'], capture_output=True,
                            text=True, encoding='utf-8', check=True)
    selected = json.loads(result.stdout)
    verify_files(LIVE, state['quality']['sourceSha256'])
    current = selected.get('currentProcess', {}).get('runtimeVersion')
    record = {'version': VERSION, 'installedAt': time.time(), 'source': str(SOURCE), 'target': str(LIVE),
              'nativePackage': str(installed), 'runtimeSelection': selected, 'configured': True,
              'activeDesktopVerified': False, 'restartRequired': selected.get('restartRequired', True),
              'currentDesktopBridgeVersion': current, 'previousVersion': PREVIOUS,
              'backup': previous['archive'], 'hooksTrusted': 2, 'packageFiles': len(state['package']['files']),
              'productionPython': str(PYTHON), 'productionEnvironment': state['productionPython'],
              'releaseMode': 'experimental' if state['experimentalAccepted'] else 'validated',
              'costGatePassed': state['costs']['costGatePassed'],
              'releaseGatePassed': state['costs']['releaseGatePassed'],
              'experimentalAcceptance': state['costs'].get('experimentalAcceptance'),
              'sourceSha256': state['quality']['sourceSha256'], 'rustSourceSha256': state['rust']['sourceSha256'],
              'binarySha256': state['costs']['binarySha256'], 'costSummary': 'verification/v080-cost-summary.json',
              'finalConfigSha256': digest(CONFIG), 'finalMarketplaceSha256': digest(MARKETPLACE)}
    for name in ('desktop-installation.json', 'v080-release.json'):
        write(LIVE / 'verification' / name, record)
    _checkpoint('configured-awaiting-live-verification', restartRequired=record['restartRequired'])
    return {'installed': VERSION, 'hooksTrusted': 2, 'restartRequired': record['restartRequired']}


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--install', action='store_true', help='Promote, install, trust the validated hooks, and select the runtime')
    mode.add_argument('--check', action='store_true', help='Read-only preflight (the default)')
    args = parser.parse_args()
    try:
        state = preflight()
        if not args.install:
            print(json.dumps({'ready': True, 'version': VERSION, 'mutations': False}))
            return 0
        previous = backup(state)
        promote(state, previous)
        installed = install_descriptor(state)
        trust_hooks(installed)
        print(json.dumps(enable(state, installed, previous)))
        return 0
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(json.dumps({'ready': False, 'reason': str(exc), 'checkpoint': str(LIVE / 'verification/install-progress-0.8.0.json')}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
