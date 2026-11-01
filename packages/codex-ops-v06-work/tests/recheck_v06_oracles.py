"""Recheck saved answers after a documented oracle correction, never rerun a model."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil

from model_tasks import prepare_task
from native_cli import native_cli
from run_model_benchmark import Host, native_evaluate, save_report

CORRECTED_TASKS = {'code_location_authority', 'code_location_rounding',
                   'log_diagnosis_migration', 'log_diagnosis_trace', 'log_diagnosis_compiler'}


def recheck(row):
    with tempfile.TemporaryDirectory(prefix='codex-ops-oracle-expected-') as temporary:
        expected = prepare_task(row['task'], Path(temporary) / 'expected')
    workspace = Path(row['workspace'])
    # A fresh native control host uses the original task workspace and permission mode.
    host = Host(native_cli(), workspace, Path(row['storeRoot']), [], artifact_prefix='oracle-recheck-v063-')
    try:
        host.request('initialize', {'clientInfo': {'name': 'codex-ops-oracle-recheck', 'version': '0.6.0'},
                                    'capabilities': {'experimentalApi': True}})
        host.send({'method': 'initialized'})
        return native_evaluate(host, row['task'], workspace, expected)
    finally:
        host.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    suite = json.loads(args.suite.read_text(encoding='utf-8'))
    changes = []
    for row in suite['reports']:
        if row['task'] not in CORRECTED_TASKS or row['outcome'].get('oracleVersion') == 'v06.3-frozen-semantics':
            continue
        result = recheck(row)
        changes.append({'key': row['key'], 'originalOutcome': row['outcome'], 'correctedOutcome': result})
    report = {'modelCalls': 0, 'reason': 'Prompts allowed equivalent labels/service names and path separators; source identities remain exact',
              'correctionVersion': 'v06.3-frozen-semantics', 'changes': changes}
    if args.output.exists():
        previous = json.loads(args.output.read_text())
        archive = args.output.with_name(args.output.stem + '-' + previous['correctionVersion'] + '.json')
        if not archive.exists():
            shutil.copy2(args.output, archive)
    save_report(args.output, report)
    print(json.dumps({'rechecked': len(changes), 'changedPassState': sum(x['originalOutcome']['passed'] != x['correctedOutcome']['passed'] for x in changes)}))


if __name__ == '__main__':
    main()
