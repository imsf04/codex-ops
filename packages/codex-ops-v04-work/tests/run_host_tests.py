"""Regression assertions against the actual installed Codex host."""
import json
from pathlib import Path
import subprocess
import sys
from native_cli import native_cli

root = Path(__file__).resolve().parents[1]
reports = {}
for case, mode in [('nested', 'none'), ('nested', 'continue'), ('nested', 'outer'),
                   ('nested', 'block'), ('direct', 'continue'), ('direct', 'production'),
                   ('capture', 'production')]:
    run = subprocess.run([sys.executable, str(root / 'tests/probe_host.py'), '--case', case, '--mode', mode],
                         capture_output=True, text=True, encoding='utf-8', timeout=100)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout.splitlines()[0])
    assert report['returncode'] == 0 and report['requests'] >= 2, report
    reports[f'{case}:{mode}'] = report
    print(f"{case}:{mode}: {report['outputBytes']} bytes; raw={report['rawAssertionPassed']}; error={report['scriptError']}", flush=True)

baseline = reports['nested:none']
for mode in ['none', 'continue', 'outer']:
    report = reports[f'nested:{mode}']
    assert report['rawAssertionPassed'] and not report['scriptError'], report
    assert report['outputBytes'] == baseline['outputBytes'], report
    if mode != 'none':
        assert report['hookTools'] == ['mcp__probe__fixture'], report
blocked = reports['nested:block']
assert blocked['scriptError'] and not blocked['rawAssertionPassed'] and blocked['feedbackVisible'], blocked
direct = reports['direct:continue']
assert direct['feedbackVisible'] and not direct['rawSentinelVisible'] and direct['hookTools'], direct
direct_production = reports['direct:production']
assert direct_production['outputBytes'] < baseline['outputBytes'] / 10 and not direct_production['scriptError'], direct_production
capture = reports['capture:production']
assert capture['rawAssertionPassed'] and capture['fullRoundtripPassed'] and not capture['scriptError'], capture
assert capture['outputBytes'] < baseline['outputBytes'] / 10, capture
assert capture['outputBytes'] + capture['sourceCodeBytes'] < baseline['outputBytes'] + baseline['sourceCodeBytes'], capture

summary = {'host': subprocess.check_output([native_cli(), '--version'], text=True).strip(),
           'passed': 7, 'reports': reports,
           'limitations': ['mock model, actual host', 'bytes are not tokens',
                           'shell hook probe was policy-rejected and is not enabled',
                           'no outer exec hook', 'no real-task success benchmark']}
(root / 'verification').mkdir(exist_ok=True)
(root / 'verification/host-report.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print('PASS: 7 host scenarios, including negative control and full reference reconstruction.')
