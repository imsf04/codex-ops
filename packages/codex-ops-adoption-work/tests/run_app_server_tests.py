"""Assert model-visible results from the real app-server/native gRPC stack."""
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
reports = []
for case in ['text', 'yield', 'mcp', 'error']:
    pair = []
    for compact in [False, True]:
        command = [sys.executable, str(root / 'tests/probe_app_server.py'), '--case', case]
        if compact:
            command.append('--compress')
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=70)
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout.splitlines()[-1])
        assert report['modelRequests'] >= 2 and report['inboundUnchanged'], report
        assert not report['rawChanged'], report
        if case == 'error':
            assert report['expectedError'], report
            assert bool(report['references']) == compact, report
        else:
            assert report['rawIntact'], report
            if compact:
                assert report['references'] and report['relay']['compactedFrames'] >= 2, report
        pair.append(report)
        reports.append(report)
    if case == 'error':
        assert pair[1]['modelVisibleBytes'] < pair[0]['modelVisibleBytes'] / 2
    else:
        assert pair[1]['modelVisibleBytes'] < pair[0]['modelVisibleBytes'] / 5, pair
    print(f'PASS {case}: model-visible {pair[0]["modelVisibleBytes"]} -> {pair[1]["modelVisibleBytes"]} bytes', flush=True)
summary = {'passed': 8, 'realAppServer': True, 'realNativeGrpcHost': True, 'externalModelCalls': False,
           'allInboundRequestsByteIdentical': True, 'reports': reports}
(root / 'verification/app-server-grpc-report.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
