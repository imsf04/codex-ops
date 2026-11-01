"""Separate preregistered terminal protocol screen; never modifies full132 rows."""
import hashlib
import json
from pathlib import Path
import sys

import run_v080_costs as runner

ORIGINAL_PREPARE = runner.tasks.prepare_task
ORIGINAL_TRIAL = runner.trial
ORIGINAL_ACCEPTANCE = runner.acceptance
ORIGINAL_HASHES = runner.evaluation_hashes
MANIFEST = runner.ROOT/'verification/acceptance-v080-terminal-supplement-1.json'
ADDITION = ('In PowerShell execute exactly `python run_probe.py; exit $LASTEXITCODE` '
            'to propagate the Python process exit status. Wait for the terminal result '
            'and report that original native exit status.')


def supplement_prepare(name, root):
    assert name == 'long_command_failure'
    expected = ORIGINAL_PREPARE(name, root)
    expected['spec'] += '\n\n'+ADDITION
    return expected


def supplement_trial(*args, **kwargs):
    previous = runner.tasks.prepare_task
    runner.tasks.prepare_task = supplement_prepare
    try:
        return ORIGINAL_TRIAL(*args, **kwargs)
    finally:
        runner.tasks.prepare_task = previous


def selected_schedule(*args, **kwargs):
    return [row for row in runner.schedule() if row['task']=='long_command_failure']


def acceptance():
    plan = ORIGINAL_ACCEPTANCE()
    declared = json.loads(MANIFEST.read_text(encoding='utf-8'))
    assert declared['promptAddition'] == ADDITION
    assert declared['schedule'] == selected_schedule()
    plan['pilot'] = {'attempts':9,'tasks':['long_command_failure'],'repeats':3,
                     'required':'Distinct functional protocol supplement; no release cost gate.'}
    plan['supplement'] = declared
    plan['supplementManifestSha256'] = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    return plan


def evaluation_hashes():
    source = Path(__file__)
    return {**ORIGINAL_HASHES(),source.name:hashlib.sha256(source.read_bytes()).hexdigest()}


def main():
    declared = json.loads(MANIFEST.read_text(encoding='utf-8'))
    assert ORIGINAL_HASHES() == declared['originalEvaluationSha256']
    if '--run' in sys.argv:
        original = json.loads((runner.ROOT/declared['originalReport']).read_text(encoding='utf-8'))
        assert original['complete'] and len(original['reports'])==132, 'Finish full132 first'
    runner.trial = supplement_trial
    runner.selected_schedule = selected_schedule
    runner.acceptance = acceptance
    runner.evaluation_hashes = evaluation_hashes
    if '--pilot' not in sys.argv:
        sys.argv.append('--pilot')
    runner.main()


if __name__ == '__main__':
    main()
