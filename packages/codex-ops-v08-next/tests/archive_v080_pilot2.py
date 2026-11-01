"""Freeze the second candidate and its audited receipts before further edits."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'verification', 'target', '.venv', '__pycache__', '.git', '.pytest_cache',
            '.ruff_cache', '.sandbox-secrets'}
RECEIPTS = (
    'quality/crap.json', 'quality/coverage.json', 'quality/crap.md',
    'rust-quality/latest.json', 'v080-kernel-build.json', 'v080-kernel-profile.json',
    'v080-native-final-current.json', 'v080-native-final-summary.json',
    'v080-native-final-cases.json', 'v080-native-final-workflows.json',
    'v080-native-round02.json', 'v080-native-method.md', 'v080-runtime-final-restage.json',
    'v080-native-configs-round02.json', 'v080-native-configs-round03.json',
    'acceptance-v080-round02.json', 'acceptance-v080-round03.json',
    'v080-pilot-2.json', 'v080-pilot-2-review.json', 'v080-pilot-3.json',
    'v080-pilot-delivery-audit.md', 'v080-pilot-delivery-findings.json',
    'v080-pilot-delivery-summary.json',
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def current_hashes(names):
    return {name: digest((ROOT / name).read_bytes()) for name in names}


def source_files():
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if EXCLUDED.intersection(relative.parts):
            continue
        if not path.is_file() or path.name == 'auth.json' or path.suffix in {'.log', '.pyc'}:
            continue
        yield path, relative.as_posix()


def main():
    quality_path = ROOT / 'verification/quality/crap.json'
    quality = json.loads(quality_path.read_text(encoding='utf-8'))
    expected = quality['sourceSha256']
    assert len(expected) == 95, 'Expected the frozen 95-module quality source set'
    assert current_hashes(expected) == expected, 'Candidate has diverged from measured sources'
    target = ROOT / 'verification/releases/pilot-2'
    target.mkdir(parents=True, exist_ok=False)
    archived = {}
    with zipfile.ZipFile(target / 'source.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
        for path, name in source_files():
            raw = path.read_bytes()
            archive.writestr(name, raw)
            archived[name] = digest(raw)
    with zipfile.ZipFile(target / 'source.zip') as archive:
        verified = {name: digest(archive.read(name.replace('\\', '/'))) for name in expected}
        assert verified == expected, 'Archive source hashes must match measured source hashes'
        assert archive.testzip() is None
    receipts = {}
    for name in RECEIPTS:
        source = ROOT / 'verification' / name
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        receipts[name] = digest(destination.read_bytes())
    assert current_hashes(expected) == expected, 'Candidate changed during archive creation'
    assert digest(quality_path.read_bytes()) == receipts['quality/crap.json']
    report = {'version': '0.8.0', 'pilot': 'pilot-2', 'createdAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'archive': str(target / 'source.zip'), 'sha256': digest((target / 'source.zip').read_bytes()),
              'qualitySourcesValidated': len(expected), 'sourceSha256': expected,
              'archivedFiles': len(archived), 'archiveFilesSha256': archived, 'receiptsSha256': receipts,
              'exclusions': sorted(EXCLUDED), 'privateAuthOrRawLogsIncluded': False,
              'note': 'Pilot 2 and 3 configurations/reports retained as separate receipts. Previous pilot-1 untouched.'}
    (target / 'archive.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('archive', 'sha256', 'qualitySourcesValidated', 'archivedFiles')}))


if __name__ == '__main__':
    main()
