"""Frozen 0.6.0/0.6.1 paired cost evaluation with complete paid-attempt accounting."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

from run_v06_model_benchmark import configuration, trial
import run_v06_model_benchmark as harness

ROOT = Path(__file__).resolve().parents[1]
TASKS = ('code_location', 'code_location_authority', 'log_diagnosis',
         'log_diagnosis_compiler', 'document_lookup', 'document_lookup_tariff')
COMMON = '\nFor every native exec_command, explicitly set workdir to the absolute fixture workspace. This applies to reads, writes, validation and polling setup.\n'
FORMAT_GUIDANCE = {
    'code_location_authority': '\nOutput format: override must be the property name that takes precedence, one of "suspended", "owner", "role"; do not use prose or a boolean in that field.',
    'log_diagnosis_compiler': '\nOutput format: root_cause must be the compiler error code. observed and expected must be type names (for example string, number, boolean), without explanatory prose.'}
original_prepare = harness.prepare_task


def prepare_typed_task(name, workspace):
    expected = original_prepare(name, workspace)
    expected['spec'] += FORMAT_GUIDANCE.get(name, '')
    return expected


harness.prepare_task = prepare_typed_task


def candidate():
    quality = json.loads((ROOT / 'verification/quality/crap.json').read_text())
    bundle = Path(os.environ['LOCALAPPDATA']) / 'CodexOps/runtime/0.6.1'
    manifest = json.loads((bundle / 'bundle.json').read_text())
    script = 'import hook,json; hook.runtime_status.current=lambda:{"activeForThisProcess":True}; print(json.dumps(hook._session_start()))'
    hook = json.loads(subprocess.check_output([sys.executable, '-c', script], cwd=ROOT, text=True, encoding='utf-8'))
    skill = ROOT / 'skills/compact-output/SKILL.md'
    instructions = 'The installed compact-output skill:\n' + skill.read_text(encoding='utf-8')
    guidance = hook['hookSpecificOutput']['additionalContext']
    instructions += '\nActive SessionStart guidance:\n' + guidance
    instructions += '\nSkill reference paths resolve under ' + str(skill.parent) + '.\n'
    return {'executable': str(bundle / 'bin/codex-ops-cli.exe'), 'package': str(ROOT),
            'toolCount': 8, 'instructions': instructions, 'hookGuidance': guidance,
            'sourceSha256': quality['sourceSha256'], 'stagedSha256': manifest['files'],
            'skillSha256': hashlib.sha256(skill.read_bytes()).hexdigest()}


def verify(config):
    package = Path(config['package'])
    bundle = Path(config['executable']).parents[1]
    for base, hashes in ((package, config['sourceSha256']), (bundle, config['stagedSha256'])):
        for name, digest in hashes.items():
            assert hashlib.sha256((base / name).read_bytes()).hexdigest() == digest, str(base / name)


def actions(row):
    return sum(row.get('completedItemsByType', {}).get(key, 0)
               for key in ('commandExecution', 'mcpToolCall', 'fileChange'))


def summarize(rows):
    groups = {condition: [r for r in rows if r['condition'] == condition] for condition in ('v060', 'v061')}
    result = {}
    for condition, group in groups.items():
        result[condition] = {'trials': len(group), 'passed': sum(r['outcome']['passed'] for r in group),
            'observedActions': sum(actions(r) for r in group),
            'retrievals': sum(sum(count for name, count in r.get('completedMcpTools', {}).items()
                                 if name.endswith('.ops_result')) for r in group),
            'inputTokens': sum((r.get('tokens') or {}).get('total', {}).get('inputTokens', 0) for r in group),
            'totalTokens': sum((r.get('tokens') or {}).get('total', {}).get('totalTokens', 0) for r in group)}
    pairs = []
    for old in groups['v060']:
        new = next((r for r in groups['v061'] if (r['task'], r['repeat']) == (old['task'], old['repeat'])), None)
        if new and old.get('tokens') and new.get('tokens'):
            pairs.append({'task': old['task'], 'repeat': old['repeat'],
                          'bothPassed': old['outcome']['passed'] and new['outcome']['passed'],
                          'actionChange': actions(new) - actions(old),
                          'inputChangePercent': 100 * (new['tokens']['total']['inputTokens'] /
                                                      old['tokens']['total']['inputTokens'] - 1)})
    result['pairs'] = pairs
    result['medianPairedInputChangePercent'] = statistics.median(p['inputChangePercent'] for p in pairs) if pairs else None
    result['gatePassed'] = bool(len(rows) == 24 and len(pairs) == 12
        and all(r.get('eligibleForComparison') for r in rows)
        and result['v061']['passed'] == 12
        and result['v061']['observedActions'] < result['v060']['observedActions']
        and result['v061']['inputTokens'] < result['v060']['inputTokens']
        and result['medianPairedInputChangePercent'] < 0)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--report', default='verification/v061-costs-final.json')
    args = parser.parse_args()
    if not args.run:
        parser.error('Use --run to execute 24 real-model trials')
    destination = ROOT / args.report
    assert not destination.exists(), 'Retain every paid attempt; use a distinct report for a new candidate'
    configs = {'v060': configuration('v06'), 'v061': candidate()}
    for config in configs.values():
        config['instructions'] += COMMON
        verify(config)
    model = json.loads((ROOT.parent / 'codex-ops/verification/model-v06-suite.json').read_text())['model']
    root = Path(tempfile.mkdtemp(prefix='codex-ops-v061-costs-'))
    (root / 'workspaces').mkdir()
    report = {'version': '0.6.1', 'model': model, 'root': str(root), 'startedAt': time.time(),
              'configurations': configs, 'reports': [], 'schedule': [], 'complete': False,
              'metrics': 'Observed commandExecution + mcpToolCall + fileChange items; outer functions.exec wrappers are not separately reported by this host. All token usage includes cached input.',
              'formatGuidance': FORMAT_GUIDANCE,
              'limits': 'Six small task instances, two repeats; no general workload or causal wall-time claim. Both arms explicitly set command workdir and receive the same explicit field-representation requirements. Original strict oracle and every failed paid attempt retained. Earlier discovery-defect pilot is retained separately as v061-costs.json.'}
    def save():
        report['summary'] = summarize(report['reports'])
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with ThreadPoolExecutor(max_workers=2) as pool:
        for repeat in (1, 2):
            for index, task in enumerate(TASKS):
                order = ('v060', 'v061') if (repeat + index) % 2 else ('v061', 'v060')
                items = [{'key': f'{repeat}-{task}-{condition}', 'task': task,
                          'repeat': repeat, 'condition': condition} for condition in order]
                report['schedule'].extend(items)
                save()
                futures = [pool.submit(trial, root, item, configs[item['condition']], model, 240) for item in items]
                for future in as_completed(futures):
                    row = future.result()
                    report['reports'].append(row)
                    save()
                    print(json.dumps({'key': row['key'], 'status': row.get('turnStatus'),
                                      'passed': row['outcome']['passed'], 'actions': actions(row),
                                      'tools': row.get('completedMcpTools'), 'seconds': row['wallSeconds']}), flush=True)
    for config in configs.values():
        verify(config)
    report.update(complete=True, endedAt=time.time())
    save()
    print(json.dumps(report['summary']), flush=True)


if __name__ == '__main__':
    main()
