"""Promote this validated candidate while retaining the previous local source."""
import hashlib
import json
from pathlib import Path
import shutil
import time
import zipfile

source = Path(__file__).resolve().parents[1]
target = source.parent / 'codex-ops'
assert source.name == 'codex-ops-v05-work' and target.is_dir()
assert json.loads((target / '.codex-plugin/plugin.json').read_text())['version'] == '0.4.0'
quality = json.loads((source / 'verification/quality/crap.json').read_text())
assert quality['above6'] == 0 and quality['functionCount'] == 430
for name, expected in quality['sourceSha256'].items():
    assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name
for name, count in [('desktop-runtime-report.json', 10), ('shell-host-report.json', 9),
                    ('host-report.json', 7), ('code-host-report.json', 10)]:
    report = source / 'verification' / name
    assert report.stat().st_mtime > time.time() - 7200, name
    assert json.loads(report.read_text())['passed'] == count, name
def excluded(path):
    return any(x in ('.venv', '__pycache__', '.git') for x in path.parts) or (
        path.name.startswith('.coverage') and path.name != '.coveragerc')
archive = target / 'verification/source-0.4.0.zip'
assert not archive.exists(), 'Retain existing backup; inspect before retrying'
old_hashes = {}
with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as backup:
    for path in target.rglob('*'):
        relative = path.relative_to(target)
        if path.is_file() and 'verification' not in relative.parts and not excluded(relative):
            backup.write(path, str(relative))
            old_hashes[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
count = 0
for path in source.rglob('*'):
    relative = path.relative_to(source)
    if path.is_file() and not excluded(relative):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        count += 1
receipt = {'version': '0.5.0', 'promotedAt': time.time(), 'source': str(source),
    'target': str(target), 'filesCopied': count, 'backup': str(archive),
    'previousSourceHashes': old_hashes, 'sourceSha256': quality['sourceSha256']}
(target / 'verification/source-promotion-0.5.0.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps({'copied': count, 'backup': str(archive)}))
