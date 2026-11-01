import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'verification'
FAILED = [
    ('codex-ops-appserver-915va3xi', 'Initial invocation omitted --sandbox-workspace and retained read-only policy; not a product failure.'),
    ('codex-ops-appserver-w2t84a6n', 'Shared-home invocation used virtual AppData cwd; native CreateProcessWithLogonW returned 267.'),
    ('codex-ops-appserver-8n8kztkt', 'Canonical cwd allowed execution; PowerShell still resolved relative counter at C:/, causing denied counter creation. No duplicate execution was established.'),
]


def main():
    temp = Path(tempfile.gettempdir()).resolve()
    summary = json.loads((REPORTS / 'v080-native-final-summary.json').read_text())
    assert summary['passed'] and summary['completedCases'] == 15
    prior = []
    roots = []
    for name, reason in FAILED:
        directory = temp / name
        report = json.loads((directory / 'report.json').read_text())
        prior.append({'root': str(directory), 'reason': reason, 'report': report})
        roots.append(directory)
    for item in summary['results']:
        directory = Path(item['root']).resolve()
        assert directory.is_relative_to(temp) and directory.name.startswith('codex-ops-appserver-')
        roots.append(directory)
    (REPORTS / 'v080-native-prior-attempts.json').write_text(json.dumps(prior, indent=2), encoding='utf-8')
    archive = REPORTS / 'v080-native-raw-evidence.zip'
    assert not archive.exists(), 'Preserve any existing evidence archive'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as output:
        for directory in roots:
            for path in directory.rglob('*'):
                if path.is_file():
                    output.write(path, str(Path(directory.name) / path.relative_to(directory)))
    receipt = {'archive': str(archive), 'bytes': archive.stat().st_size,
               'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'directories': len(roots),
               'priorFailures': len(prior), 'finalPassingCases': 15,
               'limits': 'Local raw verification material; not included in plugin distribution. Shared CODEX_HOME credentials/config are outside the archived fixture roots. Separate native-scope store is not archived; its runtime exact-value assertion and event/model records remain.'}
    (REPORTS / 'v080-native-archive.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in receipt.items() if k not in ('limits','sha256')}))


if __name__ == '__main__':
    main()
