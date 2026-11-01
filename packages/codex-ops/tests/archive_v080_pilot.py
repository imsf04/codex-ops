"""Preserve the measured first candidate before evidence correctness repairs."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

root = Path(__file__).resolve().parents[1]
target = root / 'verification' / 'releases' / 'pilot-1'
target.mkdir(parents=True, exist_ok=False)
quality = json.loads((root / 'verification/quality/crap.json').read_text())
assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
           for name, digest in quality['sourceSha256'].items())
with zipfile.ZipFile(target / 'source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if path.is_file() and not {'verification','target','.venv','__pycache__','.git'}.intersection(relative.parts):
            archive.write(path, relative)
for name in ('quality/crap.json','quality/coverage.json','rust-quality/latest.json',
             'v080-native-final-summary.json','v080-native-final-workflows.json',
             'v080-kernel-build.json','v080-native-configs.json','acceptance-v080.json'):
    destination = target / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / 'verification' / name, destination)
print(json.dumps({'archive':str(target / 'source.zip'),'modules':len(quality['sourceSha256']),
                  'sha256':hashlib.sha256((target / 'source.zip').read_bytes()).hexdigest()}))
