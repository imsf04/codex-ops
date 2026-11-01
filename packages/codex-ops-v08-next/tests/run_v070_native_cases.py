"""Serial native regressions with every attempt retained; no model billing."""
import json
from pathlib import Path
import subprocess
import sys
import argparse

ROOT = Path(__file__).resolve().parents[1]
CASES = ('text', 'error', 'yield', 'mcp', 'media', 'tool_error', 'shell', 'runtime_status',
         'progress', 'retrieval', 'grouped', 'native_scope', 'workflow_native', 'workflow_delivery')
workspace = (ROOT / 'verification/v070-native-workspace.txt').read_text()
shim = Path.home() / 'AppData/Local/CodexOps/runtime/0.7.0/bin/codex.exe'
parser = argparse.ArgumentParser()
parser.add_argument('--output', default='v070-native-cases.json')
parser.add_argument('--cases', nargs='+', choices=CASES, default=CASES)
args = parser.parse_args()
assert Path(args.output).name == args.output, 'Output must be a receipt filename'
destination = ROOT / 'verification' / args.output
assert not destination.exists(), 'Retain the existing receipt; choose a new output name'
reports = []
for case in args.cases:
    command = [sys.executable, str(ROOT / 'tests/probe_app_server.py'), '--case', case, '--compress',
               '--shim', '--shim-path', str(shim), '--production-status', '--sandbox-workspace', workspace]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=120)
    attempt = {'case': case, 'exitCode': result.returncode, 'stderr': result.stderr}
    try:
        attempt['report'] = json.loads(result.stdout)
    except ValueError:
        attempt['stdout'] = result.stdout
    reports.append(attempt)
    destination.write_text(json.dumps(reports, indent=2), encoding='utf-8')
    print(json.dumps({'case': case, 'exitCode': result.returncode,
                      'rawIntact': attempt.get('report', {}).get('rawIntact'),
                      'root': attempt.get('report', {}).get('root')}), flush=True)
