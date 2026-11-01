"""Build the local native-plugin descriptor without copying runtimes or private receipts."""
import hashlib
import json
from pathlib import Path
import shutil

source = Path(__file__).resolve().parents[1]
version = json.loads((source / '.codex-plugin/plugin.json').read_text())['version']
assert version == '0.7.0'
costs = json.loads((source / 'verification/v070-cost-summary.json').read_text())
accepted = costs['releaseGatePassed'] or costs.get('experimentalAcceptance', {}).get('userApproved', False)
assert costs.get('finalCandidate') and accepted, 'Package only the final accepted candidate'
target = source.parent / 'codex-ops-plugin' / version
assert not target.exists(), 'Keep the immutable package; inspect before rebuilding'
target.mkdir(parents=True)
for name in ('.codex-plugin', 'hooks', 'skills', 'docs'):
    shutil.copytree(source / name, target / name)
for name in ('.mcp.json', 'LICENSE', 'README.md', 'README.zh-CN.md', 'QUALITY.md'):
    shutil.copy2(source / name, target / name)
for name in ('quality/crap.md', 'v070-cost-summary.json'):
    destination = target / 'verification' / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / 'verification' / name, destination)
files = {path.relative_to(target).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
         for path in target.rglob('*') if path.is_file()}
assert not any(part in name.split('/') for name in files for part in ('.venv', '__pycache__'))
record = {'version': version, 'package': str(target), 'files': files,
          'bytes': sum((target / name).stat().st_size for name in files),
          'runtime': 'Existing dedicated production uv; native plugin commands point to validated live source',
          'excluded': ['development venv', 'runtime binaries', 'private configuration backups', 'raw benchmark traces']}
(source / ('verification/plugin-package-' + version + '.json')).write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps({'package': str(target), 'files': len(files), 'bytes': record['bytes']}))
