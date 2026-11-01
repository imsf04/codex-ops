"""Validate the exact staged runtime before configuring the Desktop override."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
version = json.loads((root / '.codex-plugin/plugin.json').read_text())['version']
bundle = Path(os.environ['LOCALAPPDATA']) / 'CodexOps/runtime' / version
shim = bundle / 'bin/codex-ops-cli.exe'
reports = []
for case in ['text', 'yield', 'mcp', 'error', 'media', 'tool_error', 'runtime_status', 'shell', 'progress', 'retrieval', 'grouped', 'native_scope', 'workflow_native']:
    command = [sys.executable, str(root / 'tests/probe_app_server.py'), '--shim', '--shim-path', str(shim), '--case', case, '--production-status']
    if case in ('shell', 'native_scope', 'workflow_native'):
        # Preserve existing sandbox configuration and its initialized test workspace.
        command += ['--sandbox-workspace', str(Path(os.environ['TEMP']) / 'codex-ops-probe-jrmkhnjv')]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=70)
    assert result.returncode == 0, result.stderr[-4000:]
    report = json.loads(result.stdout.splitlines()[-1])
    assert report['shim'] and report['modelRequests'] >= 2 and not report['rawChanged'], report
    if case == 'error':
        assert report['expectedError'] and report['references'], report
    else:
        assert report['rawIntact'], report
    if case in ('text', 'yield', 'mcp', 'shell'):
        assert report['references'] and report['relay']['compactedFrames'] > 0, report
    if case == 'media':
        assert report['imagePresent'] and report['relay']['compactedFrames'] == 0, report
    if case == 'tool_error':
        assert report['toolErrorPreserved'], report
    if case == 'progress':
        assert report['progressCompacted'], report
    if case == 'grouped':
        assert report['frameBudgetApplied'] and report['references'] == 16, report
    if case == 'native_scope':
        assert report['nativeScopeLoaded'], report
    if case == 'workflow_native':
        assert report['workflowNativeDiagnosed'], report
    if case == 'retrieval':
        assert report['retrievalPageIntact'], report
        reasons = report['presentationTotals']['byReason']
        assert 'explicit_retrieval' in reasons, reasons
    reports.append(report)
    print('PASS staged ' + case, flush=True)
summary = {'version': version, 'passed': len(reports), 'stagedShim': str(shim),
           'shimSha256': hashlib.sha256(shim.read_bytes()).hexdigest(),
           'realAppServer': True, 'realNativeGrpcHost': True, 'externalModelCalls': False,
           'desktopMainActivation': 'separate from this isolated launch validation', 'reports': reports}
(root / 'verification/desktop-runtime-report.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
