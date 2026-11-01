"""Archive the measured candidate for review; never install or waive gates."""
import datetime
import json
import shutil
import zipfile

from archive_v080_pilot2 import ROOT, current_hashes, digest, source_files

RECEIPTS = ('quality/crap.json', 'quality/crap.md', 'rust-quality/latest.json',
            'v080-cost-summary.json', 'v080-native-friction-current.json',
            'v080-native-final-summary.json', 'v080-runtime-friction-restage.json')
SUFFIXES = {'.py', '.rs', '.toml', '.lock', '.md', '.json', '.yaml', '.yml', '.ts', '.js', '.ps1', '.cmd', '.bat', '.txt'}


def permitted(path, name):
    if any(part.startswith('.env') for part in path.parts):
        return False
    if any(word in path.name.lower() for word in ('credential', 'secret', 'auth.json')):
        return False
    return path.suffix in SUFFIXES or path.name in ('.coveragerc', '.gitignore')


def main():
    summary = json.loads((ROOT / 'verification/v080-cost-summary.json').read_text(encoding='utf-8'))
    quality = json.loads((ROOT / 'verification/quality/crap.json').read_text(encoding='utf-8'))
    expected = quality['sourceSha256']
    assert len(expected) == 96
    assert summary['sourceSha256'] == expected == current_hashes(expected)
    assert summary['costGatePassed'] is False and summary['releaseGatePassed'] is False
    target = ROOT / 'verification/releases/review-final'
    target.mkdir(parents=True, exist_ok=False)
    files = {}
    with zipfile.ZipFile(target / 'source.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
        for path, name in source_files():
            if not permitted(path, name):
                continue
            raw = path.read_bytes()
            archive.writestr(name, raw)
            files[name] = digest(raw)
    with zipfile.ZipFile(target / 'source.zip') as archive:
        assert {name: digest(archive.read(name.replace('\\', '/'))) for name in expected} == expected
        assert archive.testzip() is None
    receipts = {}
    for name in RECEIPTS:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'verification' / name, destination)
        receipts[name] = digest(destination.read_bytes())
    assert current_hashes(expected) == expected
    report = {'version': '0.8.0', 'purpose': 'review-only',
              'createdAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'archive': str(target / 'source.zip'), 'sha256': digest((target / 'source.zip').read_bytes()),
              'qualitySourcesValidated': 96, 'sourceSha256': expected,
              'archiveFilesSha256': files, 'receiptsSha256': receipts,
              'privateAuthOrRawLogsIncluded': False, 'runtimeBinariesIncluded': False,
              'costGatePassed': False, 'releaseGatePassed': False, 'installed': False,
              'exclusions': ['verification/raw traces', 'private credentials', 'venv', 'target', 'runtime binaries']}
    (target / 'archive.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('archive', 'sha256', 'qualitySourcesValidated', 'installed')}))


if __name__ == '__main__':
    main()
