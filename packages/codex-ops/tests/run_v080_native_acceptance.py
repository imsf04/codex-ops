import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CASES = ['text', 'error', 'yield', 'mcp', 'media', 'tool_error', 'shell', 'runtime_status',
         'progress', 'retrieval', 'grouped', 'native_scope', 'workflow_native', 'workflow_delivery', 'v080']


def assess(report):
    checks = {'rawUnchanged': not report['rawChanged'], 'sharedHomeUnchanged': report['sharedConfigAuthUnchanged'],
              'sameWorkspace': report['sandboxWorkspaceSameFile'], 'workspaceWrite': report['sandboxMode'] == 'workspace-write',
              'activeShim': report.get('shim') is True}
    case = report['case']
    checks['expectedOutcome'] = report['expectedError'] if case == 'error' else report['rawIntact']
    extra = {'media': 'imagePresent', 'tool_error': 'toolErrorPreserved', 'progress': 'progressCompacted',
             'retrieval': 'retrievalPageIntact', 'grouped': 'frameBudgetApplied', 'native_scope': 'nativeScopeLoaded',
             'workflow_native': 'workflowNativeDiagnosed', 'workflow_delivery': 'workflowDeliveryIntact'}
    if case in extra:
        checks[extra[case]] = report[extra[case]]
    if case == 'workflow_delivery':
        checks['workflowDeliveryVisible'] = report['workflowDeliveryVisible']
    if case == 'v080':
        for key in ('entryAndRecovery', 'verification', 'exactObservations', 'verificationFailureVisible',
                    'staleCurrentRecovery', 'freshRecoveryVisible'):
            checks[key] = report['v080'][key]
        checks['directEvidenceOperations'] = {'investigate', 'evidence', 'verify'}.issubset(report['v080']['directOperations'])
        checks['noOuterReferences'] = report['v080']['outerReferenceBlocks'] == 0
        observed = report['v080'].get('nativeObservations') or {}
        checks['oneExecutionAndPolling'] = observed.get('executions') == 1 and observed.get('polls', 0) >= 1
        checks['fullLongObservation'] = observed.get('outputCharacters', 0) > 8192 and observed.get('observationsExact') is True
    return {'passed': all(checks.values()), 'checks': checks}


def execute(case, args, directory):
    command = [sys.executable, str(ROOT / 'tests/probe_app_server.py'), '--case', case, '--shim',
               '--shim-path', str(args.shim), '--shared-home', str(args.shared_home),
               '--sandbox-workspace', str(args.workspace)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=150)
    (directory / (case + '.stdout')).write_text(result.stdout, encoding='utf-8')
    (directory / (case + '.stderr')).write_text(result.stderr, encoding='utf-8')
    if result.returncode:
        return {'case': case, 'passed': False, 'returncode': result.returncode,
                'stdout': str(directory / (case + '.stdout')), 'stderr': str(directory / (case + '.stderr'))}
    report = json.loads(result.stdout.splitlines()[-1])
    (directory / (case + '.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    return {'case': case, **assess(report), 'root': report['root'], 'report': str(directory / (case + '.json'))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--shared-home', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--shim', type=Path, default=Path(os.environ['LOCALAPPDATA']) / 'CodexOps/runtime/0.8.0/bin/codex.exe')
    parser.add_argument('--cases', nargs='+', choices=CASES, default=CASES)
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')
    directory = ROOT / 'verification/v080-native-attempts' / stamp
    directory.mkdir(parents=True)
    records = []
    for case in args.cases:
        record = execute(case, args, directory)
        records.append(record)
        (directory / 'cases.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
        print(json.dumps({'case': case, 'passed': record['passed'], 'artifact': record.get('root', record.get('stderr'))}), flush=True)
        if not record['passed']:
            break
    summary = {'version': '0.8.0', 'sharedHome': str(args.shared_home), 'workspace': str(args.workspace),
               'runtime': str(args.shim), 'requestedCases': args.cases, 'completedCases': len(records),
               'passed': len(records) == len(args.cases) and all(r['passed'] for r in records),
               'results': records, 'scope': 'Deterministic localhost model, actual native app-server/Code Mode/staged runtime, shared official sandbox state; no paid model.'}
    (directory / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    if args.cases == CASES and summary['passed']:
        (ROOT / 'verification/v080-native-final-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        (ROOT / 'verification/v080-native-final-cases.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    print(json.dumps({'passed': summary['passed'], 'summary': str(directory / 'summary.json')}), flush=True)
    raise SystemExit(0 if summary['passed'] else 1)


if __name__ == '__main__':
    main()
