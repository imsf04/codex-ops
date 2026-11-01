"""Promote the fully verified local candidate without modifying old runtime bundles."""
import hashlib
import json
from pathlib import Path
import shutil
import time
import zipfile

source = Path(__file__).resolve().parents[1]
target = source.parent / 'codex-ops'
assert source.name == 'codex-ops-v06-work'
assert json.loads((target / '.codex-plugin/plugin.json').read_text())['version'] == '0.5.0'
quality = json.loads((source / 'verification/quality/crap.json').read_text())
assert quality['above6'] == 0
for name, expected in quality['sourceSha256'].items():
    assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name
runtime = json.loads((source / 'verification/desktop-runtime-report.json').read_text())
assert runtime['version'] == '0.6.0' and runtime['passed'] == 13
comparison = json.loads((source / 'verification/v06-model-comparison.json').read_text())
assert comparison['complete'] and comparison['completedTrials'] == 120
def excluded(path):
    return any(x in ('.venv', '__pycache__', '.git') for x in path.parts) or (
        path.name.startswith('.coverage') and path.name != '.coveragerc')
backup = target / 'verification/source-0.5.0.zip'
assert not backup.exists(), 'Retain an existing backup and inspect before retrying'
with zipfile.ZipFile(backup, 'x', zipfile.ZIP_DEFLATED) as archive:
    for path in target.rglob('*'):
        relative = path.relative_to(target)
        if path.is_file() and 'verification' not in relative.parts and not excluded(relative):
            archive.write(path, str(relative))
copied = 0
for path in source.rglob('*'):
    relative = path.relative_to(source)
    if path.is_file() and not excluded(relative):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        copied += 1
record = {'version': '0.6.0', 'promotedAt': time.time(), 'source': str(source),
          'target': str(target), 'backup': str(backup), 'filesCopied': copied,
          'sourceSha256': quality['sourceSha256']}
(target / 'verification/source-promotion-0.6.0.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps({'version': '0.6.0', 'copied': copied, 'backup': str(backup)}))
