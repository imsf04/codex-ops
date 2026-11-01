"""Collect exact final-bundle probes without rerunning passed source operations."""
import hashlib
import json
import os
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
freeze = json.loads((root / 'verification/v06-source-freeze.json').read_text())
cases = ['text', 'yield', 'mcp', 'error', 'media', 'tool_error', 'runtime_status',
         'shell', 'progress', 'retrieval', 'grouped', 'native_scope', 'workflow_native']
found = {}
for folder in Path(os.environ['TEMP']).glob('codex-ops-appserver-*'):
    path = folder / 'report.json'
    status = folder / 'shim-bridge-status.json'
    if not path.is_file() or not status.is_file():
        continue
    if path.stat().st_mtime < freeze['frozenAt']:
        continue
    report = json.loads(path.read_text(encoding='utf-8'))
    identity = json.loads(status.read_text(encoding='utf-8'))
    case = report['case']
    if case not in cases or identity.get('runtimeVersion') != '0.6.0':
        continue
    if not report.get('productionStatusDirectory') or not report.get('shim'):
        continue
    previous = found.get(case)
    if previous is None or path.stat().st_mtime > previous[0]:
        found[case] = (path.stat().st_mtime, report)
assert set(found) == set(cases), set(cases) - set(found)
reports = [found[case][1] for case in cases]
for report in reports:
    case = report['case']
    assert report['modelRequests'] >= 2 and not report['rawChanged'], report
    if case == 'error':
        assert report['expectedError'] and report['references'], report
    else:
        assert report['rawIntact'], report
    if case in ('text', 'yield', 'mcp', 'shell'):
        assert report['references'] and report['relay']['compactedFrames'] > 0
    if case == 'media':
        assert report['imagePresent'] and report['relay']['compactedFrames'] == 0
    for name, flag in [('tool_error', 'toolErrorPreserved'), ('progress', 'progressCompacted'),
                       ('retrieval', 'retrievalPageIntact'), ('grouped', 'frameBudgetApplied'),
                       ('native_scope', 'nativeScopeLoaded'), ('workflow_native', 'workflowNativeDiagnosed')]:
        if case == name:
            assert report[flag], report
bundle = Path(os.environ['LOCALAPPDATA']) / 'CodexOps/runtime/0.6.0'
for name, expected in freeze['stagedSha256'].items():
    assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == expected
summary = {'version': '0.6.0', 'passed': len(reports), 'verifiedAt': time.time(),
    'realAppServer': True, 'realNativeGrpcHost': True, 'externalModelCalls': False,
    'stagedShim': str(bundle / 'bin/codex-ops-cli.exe'), 'stagedHashesVerified': len(freeze['stagedSha256']),
    'desktopMainActivation': 'Separate from these isolated launches; requires full Desktop restart',
    'consolidation': 'Latest per-case production-status probe after immutable final bundle freeze; every assertion rechecked',
    'retainedFailedProbe': {'root': 'C:/Users/imsfp/AppData/Local/Temp/codex-ops-appserver-ktun1uqi',
        'cause': 'Test command lacked explicit PowerShell exit $LASTEXITCODE; native shell reported1 while fixture expected7. SDK preserved native1 and diagnosis correctly; corrected command verified native7.'},
    'reports': reports}
(root / 'verification/desktop-runtime-report.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps({'passed': len(reports), 'stagedHashesVerified': len(freeze['stagedSha256'])}))
