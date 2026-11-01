"""Install the validated personal plugin using the native host and existing uv runtime."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

from host_rpc import call

source = Path(__file__).resolve().parents[1]
target = source.parent / 'codex-ops'
version = '0.6.1'
quality = json.loads((source / 'verification/quality/crap.json').read_text())
costs = json.loads((source / 'verification/v061-cost-summary.json').read_text())
assert quality['above6'] == 0 and costs['releaseGatePassed'] and costs['finalCandidate']
assert costs['sourceSha256'] == quality['sourceSha256']
for name, digest in quality['sourceSha256'].items():
    assert hashlib.sha256((source / name).read_bytes()).hexdigest() == digest, name
assert json.loads((target / '.codex-plugin/plugin.json').read_text())['version'] == '0.6.0'
previous_quality = json.loads((target / 'verification/quality/crap.json').read_text())
for name, digest in previous_quality['sourceSha256'].items():
    assert hashlib.sha256((target / name).read_bytes()).hexdigest() == digest, 'Live source changed: ' + name
package = json.loads((source / 'verification/plugin-package-0.6.1.json').read_text())
package_root = Path(package['package'])
for name, digest in package['files'].items():
    assert hashlib.sha256((package_root / name).read_bytes()).hexdigest() == digest, name

backup = target / 'verification/source-0.6.0.zip'
assert not backup.exists(), 'Preserve the original release backup and inspect before retrying'
with zipfile.ZipFile(backup, 'x', zipfile.ZIP_DEFLATED) as archive:
    for path in target.rglob('*'):
        rel = path.relative_to(target)
        excluded = any(part in ('.venv', '__pycache__', '.git', 'verification') for part in rel.parts)
        excluded = excluded or (path.name.startswith('.coverage') and path.name != '.coveragerc')
        if path.is_file() and not excluded:
            archive.write(path, str(rel))
old_receipts = target / 'verification/releases/0.6.0'
old_receipts.mkdir(parents=True, exist_ok=False)
for name in ('desktop-installation.json', 'desktop-live-0.6.0.json', 'quality/crap.json', 'quality/coverage.json'):
    destination = old_receipts / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target / 'verification' / name, destination)
for path in source.rglob('*'):
    rel = path.relative_to(source)
    excluded = any(part in ('.venv', '__pycache__', '.git') for part in rel.parts)
    excluded = excluded or (path.name.startswith('.coverage') and path.name != '.coveragerc')
    if path.is_file() and not excluded:
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

marketplace = Path.home() / '.agents/plugins/marketplace.json'
shutil.copy2(marketplace, target / 'verification/marketplace-before-0.6.1.json')
registry = json.loads(marketplace.read_text(encoding='utf-8'))
entries = [entry for entry in registry['plugins'] if entry['name'] == 'codex-ops']
assert len(entries) == 1
entries[0]['source']['path'] = './code/dsh-ops/packages/codex-ops-plugin/0.6.1'
marketplace.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
shim = Path.home() / 'AppData/Local/CodexOps/runtime/0.6.1/bin/codex.exe'
subprocess.run([str(shim), 'plugin', 'add', 'codex-ops@personal', '--json'], check=True)
installed = Path.home() / '.codex/plugins/cache/personal/codex-ops/0.6.1'
for name, digest in package['files'].items():
    assert hashlib.sha256((installed / name).read_bytes()).hexdigest() == digest, name
print('Native package installed and verified', flush=True)

shutil.copy2(Path.home() / '.codex/config.toml', target / 'verification/config-before-0.6.1.toml')
before = call('hooks/list', {})
hooks = [hook for group in before['result']['data'] for hook in group['hooks']
         if hook.get('pluginId') == 'codex-ops@personal']
assert len(hooks) == 2
for hook in hooks:
    assert '\\0.6.1\\' in hook['sourcePath'], hook['sourcePath']
    definition, contents = hook['currentHash'].split('/')
    result = call('config/value/write', {'keyPath': 'hooks.state.' + json.dumps(hook['key']),
        'mergeStrategy': 'upsert', 'value': {'trusted_hash': definition, 'trusted_content_hash': contents}})
    assert 'error' not in result, result
after = call('hooks/list', {})
hooks = [hook for group in after['result']['data'] for hook in group['hooks']
         if hook.get('pluginId') == 'codex-ops@personal']
assert len(hooks) == 2 and all(h['enabled'] and h['trustStatus'] == 'trusted' for h in hooks)
(target / 'verification/native-hooks-0.6.1.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
enabled = subprocess.run([sys.executable, str(target / 'runtime_bridge/control.py'), 'enable'],
                         capture_output=True, text=True, encoding='utf-8', check=True)
selection = json.loads(enabled.stdout)
for name, digest in quality['sourceSha256'].items():
    assert hashlib.sha256((target / name).read_bytes()).hexdigest() == digest, name
record = {'version': version, 'installedAt': time.time(), 'source': str(source), 'target': str(target),
          'nativePackage': str(installed), 'runtimeSelection': selection,
          'configured': True, 'activeDesktopVerified': False, 'restartRequired': True,
          'currentDesktopBridgeVersion': '0.6.0', 'previousVersion': '0.6.0',
          'backup': str(backup), 'hooksTrusted': len(hooks), 'packageFiles': len(package['files']),
          'costs': costs, 'sourceSha256': quality['sourceSha256']}
for name in ('v061-release.json', 'desktop-installation.json'):
    (target / 'verification' / name).write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps({'installed': version, 'hooksTrusted': len(hooks), 'restartRequired': True}), flush=True)
