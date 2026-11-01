"""Assert Bash presentation, status, polling and code-mode behavior in real Codex."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from native_cli import native_cli

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from store import Store

parser = argparse.ArgumentParser()
parser.add_argument('--workspace')
args = parser.parse_args()
workspace = args.workspace
reports = []
cases = ['shell_direct', 'shell_fail_direct', 'shell_silent_fail_direct',
         'shell_nested', 'shell_fail_nested', 'shell_long_direct', 'shell_long_fail_direct',
         'shell_long_nested', 'shell_long_fail_nested']
for case in cases:
    command = [sys.executable, str(root / 'tests/probe_host.py'), '--case', case, '--mode', 'observe', '--persist-test']
    if workspace:
        command += ['--workspace', workspace]
    run = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=100)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout.splitlines()[0])
    folder = Path(report['root'])
    workspace = workspace or report['root']
    outputs = json.loads((folder / 'outputs.json').read_text(encoding='utf-8'))
    hook_events = [json.loads(line) for line in (folder / 'hooks.jsonl').read_text(encoding='utf-8').splitlines()]
    decisions = [json.loads(line) for line in (folder / 'decisions.jsonl').read_text(encoding='utf-8').splitlines()]
    assert report['returncode'] == 0 and not report['scriptError'], report
    assert report['hookTools'] == ['Bash'], report  # Exactly once, at process completion.
    decision = decisions[0]['output']
    if 'fail' in case:
        assert decision is None, (case, decision)
    else:
        assert decision and decision.get('continue') is False and 'decision' not in decision, (case, decision)
        receipt = json.loads(decision['stopReason'])
        assert receipt['metadata']['exit_code'] == 0 and receipt['metadata']['executionComplete'], receipt
        assert receipt['metadata']['observationScope'] == ('final-chunk' if 'long' in case else 'execution-output'), receipt
        saved = Store(folder / 'store')
        try:
            assert saved.get(receipt['ref']) == hook_events[0]['tool_response']
        finally:
            saved.close()
    if '_nested' in case:
        assert report['shellRawPassed'], report
        parts = next(json.loads(block['text']) for block in outputs[-1]['output']
                     if block.get('text', '').startswith('[{"chunk_id"'))
        assert parts[-1]['output'] == hook_events[0]['tool_response'], 'Nested output changed after PostToolUse'
        assert parts[-1]['exit_code'] == (7 if 'fail' in case else 0), 'Nested exit code changed'
        # Large raw text still exists outside the hook because exec is not intercepted.
        assert report['outputBytes'] > 30000, report
    else:
        final = outputs[-1]['output']
        if 'fail' in case:
            assert 'Process exited with code 7' in final, final[:300]
            assert 'PHASE_2_END' in final and 'ops://' not in final, final[:300]
            if 'silent' not in case:
                assert 'STDERR_FAILURE_SENTINEL' in final
        else:
            assert json.loads(final)['metadata']['exit_code'] == 0, final[:300]
            assert len(final.encode()) < 6000
        if 'long' in case:
            assert len(outputs) >= 3
            assert all('Process running with session ID' in x['output'] for x in outputs[:-1])
            ids = [re.search(r'Process running with session ID (\d+)', x['output'])[1] for x in outputs[:-1]]
            assert len(set(ids)) == 1
    reports.append({'case': case, **report, 'compressed': decision is not None})
    print(f'PASS {case}: {report["outputBytes"]} bytes; raw={report["shellRawPassed"]}; compressed={decision is not None}', flush=True)

summary = {'passed': len(reports), 'host': subprocess.check_output([native_cli(), '--version'], text=True).strip(),
           'workspace': workspace, 'reports': reports,
           'boundary': 'Completion only; native transcript correlation required; failures/in-progress unchanged; outer exec not intercepted.'}
(root / 'verification').mkdir(exist_ok=True)
(root / 'verification/shell-host-report.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(f'PASS {len(reports)} native Bash scenarios')
