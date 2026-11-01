"""Verify every staged runtime contract before selecting the Desktop override."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
shim = Path.home() / 'AppData/Local/CodexOps/runtime/0.6.1/bin/codex-ops-cli.exe'
reports = [json.loads((root / 'verification/v061-delivery-native.json').read_text())]
previous = root / 'verification/v061-native-runtime.json'
if previous.exists():
    attempts = json.loads(previous.read_text())['reports']
    archive = root / 'verification/v061-native-runtime-initial-probe.json'
    if not archive.exists():
        archive.write_text(json.dumps(attempts, indent=2), encoding='utf-8')
    reports = [row for row in attempts if row['expectedError'] or row['rawIntact']]
workspace = Path(tempfile.mkdtemp(prefix='codex-ops-v061-runtime-'))
cases = ('text', 'yield', 'mcp', 'error', 'media', 'tool_error', 'shell',
         'runtime_status', 'progress', 'retrieval', 'grouped', 'native_scope', 'workflow_native')
for case in cases:
    if any(row['case'] == case for row in reports):
        continue
    result = subprocess.run([sys.executable, 'tests/probe_app_server.py', '--shim',
        '--shim-path', str(shim), '--production-status', '--sandbox-workspace', str(workspace), '--case', case], cwd=root,
        capture_output=True, text=True, encoding='utf-8', timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr)
    report = json.loads(result.stdout.splitlines()[-1])
    reports.append(report)
    (root / 'verification/v061-native-runtime.json').write_text(json.dumps(
        {'version': '0.6.1', 'reports': reports, 'complete': len(reports) == 14}, indent=2), encoding='utf-8')
    assert report['expectedError'] if case == 'error' else report['rawIntact'], report
    assert not report['rawChanged'], report
    for name, field in (('media', 'imagePresent'), ('tool_error', 'toolErrorPreserved'),
                        ('progress', 'progressCompacted'), ('retrieval', 'retrievalPageIntact'),
                        ('grouped', 'frameBudgetApplied'), ('native_scope', 'nativeScopeLoaded'),
                        ('workflow_native', 'workflowNativeDiagnosed')):
        if case == name:
            assert report[field], report
    print('PASS staged ' + case, flush=True)
print('14 staged runtime cases passed', flush=True)
