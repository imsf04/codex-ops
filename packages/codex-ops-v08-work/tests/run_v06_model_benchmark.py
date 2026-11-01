"""Resumable 20-task, two-repeat, three-condition native model evaluation."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid

from model_tasks import all_tasks, prepare_task, evaluate_task
from native_cli import native_cli
from run_model_benchmark import Host, native_evaluate, save_report

PACKAGE = Path(__file__).resolve().parents[1]
CONDITIONS = ('native', 'v05', 'v06')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configuration(condition):
    if condition == 'native':
        return {'executable': native_cli(), 'package': None, 'toolCount': 0, 'instructions': ''}
    version = {'v05': '0.5.0', 'v06': '0.6.0'}[condition]
    package = PACKAGE.parent / ('codex-ops-v05-work' if condition == 'v05' else 'codex-ops-v06-work')
    bundle = Path(os.environ['LOCALAPPDATA']) / 'CodexOps/runtime' / version
    receipt = json.loads((bundle / 'bundle.json').read_text())
    for name, expected in receipt['files'].items():
        assert digest(bundle / name) == expected, 'Staged bundle changed: ' + name
    quality = json.loads((package / 'verification/quality/crap.json').read_text())
    for name, expected in quality['sourceSha256'].items():
        assert digest(package / name) == expected, 'Measured source changed: ' + name
    skill = package / 'skills/compact-output/SKILL.md'
    hook_command = 'import hook,json; hook.runtime_status.current=lambda:{"activeForThisProcess":True}; print(json.dumps(hook._session_start()))'
    hook = json.loads(subprocess.check_output([sys.executable, '-c', hook_command], cwd=package, text=True, encoding='utf-8'))
    guidance = hook['hookSpecificOutput']['additionalContext']
    instructions = 'The following is this installed candidate\'s compact-output skill:\n' + skill.read_text(encoding='utf-8')
    instructions += '\nThe matching active SessionStart guidance is:\n' + guidance
    instructions += '\nSkill reference paths resolve under ' + str(skill.parent) + '.\n'
    return {'executable': str(bundle / 'bin/codex-ops-cli.exe'), 'package': str(package),
            'toolCount': 6 if condition == 'v05' else 8, 'instructions': instructions,
            'sourceSha256': quality['sourceSha256'], 'stagedSha256': receipt['files'],
            'skillSha256': digest(skill), 'hookGuidance': guidance}


def mcp_flags(package, store):
    values = ['mcp_servers.ops_bench.command=' + json.dumps(sys.executable),
              'mcp_servers.ops_bench.args=' + json.dumps([str(Path(package) / 'server.py')]),
              'mcp_servers.ops_bench.enabled=true', 'mcp_servers.ops_bench.startup_timeout_sec=30',
              'mcp_servers.ops_bench.tool_timeout_sec=60',
              'mcp_servers.ops_bench.env.CODEX_OPS_STORE=' + json.dumps(str(store)),
              'mcp_servers.ops_bench.env.CODEX_OPS_MEASUREMENT_ORIGIN="validation"']
    return [argument for value in values for argument in ('-c', value)]


def schedule(repeats):
    tasks = list(all_tasks())
    random.Random(606).shuffle(tasks)
    rows = []
    for repeat in range(repeats):
        for index, task in enumerate(tasks):
            shift = (index + repeat) % 3
            for condition in CONDITIONS[shift:] + CONDITIONS[:shift]:
                rows.append({'key': f'{repeat + 1}-{task}-{condition}', 'task': task,
                             'repeat': repeat + 1, 'condition': condition})
    return rows


def trial(run_root, item, config, model, timeout):
    attempt_name = item['key'] + (f'-attempt{item["attemptNumber"]}' if item.get('attemptNumber', 1) > 1 else '')
    workspace = run_root / 'workspaces' / attempt_name
    expected = prepare_task(item['task'], workspace)
    expected_path = run_root / 'expectations' / (item['key'] + '.json')
    expected_path.parent.mkdir(exist_ok=True)
    expected_path.write_text(json.dumps({key: value for key, value in expected.items()
                                        if key != 'selfTestSolution'}, ensure_ascii=False), encoding='utf-8')
    before = evaluate_task(item['task'], workspace, expected)
    assert not before['passed'], 'Unsolved fixture unexpectedly passed'
    store = Path(os.environ['LOCALAPPDATA']) / 'CodexOps/verification/model-v06' / run_root.name / attempt_name
    store.mkdir(parents=True, exist_ok=True)
    flags = mcp_flags(config['package'], store) if config['package'] else []
    host = Host(config['executable'], workspace, store, flags)
    started = time.monotonic()
    start_time = time.time()
    try:
        report = host.run(workspace, model, timeout, expected['spec'],
                          instructions=config['instructions'], expected_tool_count=config['toolCount'])
    except Exception as exc:
        report = {'turnStatus': 'incomplete', 'error': str(exc), 'tokens': host.tokens,
                  'completedItemsByType': dict(host.items), 'completedMcpTools': dict(host.tools),
                  'nativeMethodsObserved': dict(host.methods), 'agentMessages': host.agent_messages}
    elapsed = round(time.monotonic() - started, 3)
    try:
        clean = {key: value for key, value in expected.items() if key != 'selfTestSolution'}
        outcome = native_evaluate(host, item['task'], workspace, clean)
    except Exception as exc:
        outcome = {'passed': False, 'checks': 0, 'evaluationBlocked': True, 'error': str(exc)}
    finally:
        host.close()
    sys.path.insert(0, str(PACKAGE))
    from telemetry import snapshot
    presentation = snapshot('validation', store)
    observed = presentation.get('totals', {}).get('items', 0) > 0
    stderr = host.stderr_path.read_text(encoding='utf-8')
    blocked = 'orchestrator_helper_' in stderr or 'Native sandbox is not ready:' in report.get('error', '')
    blocked = blocked or 'orchestrator_helper_' in outcome.get('error', '')
    valid = observed == bool(config['package']) and not blocked and not outcome.get('evaluationBlocked')
    return {**item, **report, 'outcome': outcome, 'before': before, 'wallSeconds': elapsed,
            'startedAt': start_time, 'endedAt': time.time(), 'workspace': str(workspace),
            'expectedPath': str(expected_path),
            'eventsPath': str(host.events_path), 'stderrPath': str(host.stderr_path), 'storeRoot': str(store),
            'presentation': presentation, 'bridgeObserved': observed, 'environmentBlocked': blocked,
            'eligibleForComparison': bool(valid and report.get('tokens') and report.get('turnStatus') == 'completed'),
            'treatmentValid': observed == bool(config['package']),
            'workspaceLayout': 'ordinary Path.mkdir Temp workspace; ordinary AppData Local cache',
            'policy': 'native workspace-write; approval never; no fallback',
            'guidanceMode': 'actual version skill and active SessionStart text through developerInstructions; hooks not executed' if config['package'] else 'native baseline; no OPS guidance',
            'instructionsSha256': hashlib.sha256(config['instructions'].encode()).hexdigest()}


def totals(rows):
    known = [(row.get('tokens') or {}).get('total', {}) for row in rows]
    return {'completed': len(rows), 'passed': sum(row['outcome']['passed'] for row in rows),
            'totalTokens': sum(row.get('totalTokens', 0) for row in known),
            'inputTokens': sum(row.get('inputTokens', 0) for row in known),
            'cachedInputTokens': sum(row.get('cachedInputTokens', 0) for row in known),
            'wallSecondsSum': round(sum(row['wallSeconds'] for row in rows), 3)}


def recover_unexecuted(result):
    retained = []
    for row in result['reports']:
        pre_model = (not row.get('tokens') and not row.get('agentMessages') and
                     row.get('error', '').startswith('Native sandbox is not ready:'))
        if not pre_model:
            retained.append(row)
            continue
        result.setdefault('environmentAttempts', []).append({**row,
            'recoveryReason': 'Readiness failed before model execution; original failed attempt retained; first paid model trial may now start'})
        result.setdefault('attemptNumbers', {})[row['key']] = row.get('attemptNumber', 1) + 1
    result['reports'] = retained


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--output', type=Path, default=PACKAGE / 'verification/model-v06-suite.json')
    parser.add_argument('--conditions', default='native,v05')
    parser.add_argument('--tasks', default='')
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--workers', type=int, choices=(1, 2), default=2)
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--recover-unexecuted', action='store_true', help='Retain pre-model readiness failures in an explicit ledger, then start their first actual model trial')
    args = parser.parse_args()
    conditions = args.conditions.split(',')
    assert set(conditions) <= set(CONDITIONS) and args.repeats >= 2
    config = tomllib.loads((Path.home() / '.codex/config.toml').read_text(encoding='utf-8'))
    model = config['model']
    assert model == 'gpt-6.1-terra', 'Configured model changed; review comparison design before calls'
    if not args.run:
        print(json.dumps({'status': 'not-run', 'tasks': len(all_tasks()), 'repeats': args.repeats,
                          'conditions': conditions, 'plannedTrials': len(schedule(args.repeats)), 'model': model}))
        return
    configurations = {condition: configuration(condition) for condition in conditions}
    oracle = json.loads((PACKAGE / 'verification/model-v06-oracle-frozen.json').read_text())
    for name, expected in oracle['sourceSha256'].items():
        assert digest(PACKAGE / name) == expected, 'Frozen oracle changed: ' + name
    if args.resume:
        result = json.loads(args.output.read_text())
        assert result['model'] == model and result['repeats'] == args.repeats
        root = Path(result['root'])
        for condition, value in configurations.items():
            if condition in result['configurations']:
                assert result['configurations'][condition] == value, 'Candidate changed after first paid trial'
        result['configurations'].update(configurations)
    else:
        assert not args.output.exists(), 'Use --resume, never overwrite paid trials'
        root = Path(tempfile.gettempdir()) / ('codex-ops-model-v06-' + uuid.uuid4().hex)
        root.mkdir()
        result = {'version': '0.6.0', 'type': '20-distinct-tasks-two-repeat-three-condition',
                  'root': str(root), 'model': model, 'repeats': args.repeats,
                  'configurations': configurations, 'reports': [], 'schedule': schedule(args.repeats),
                  'externalModelCalls': True, 'complete': False,
                  'limitations': ['Controlled fixtures; no broad statistical superiority claim',
                      'Native baseline has no OPS guidance; enabled groups include their actual version guidance',
                      'Parallel load and cache/run order influence timings; exact start/end times retained',
                      'Unavailable conditions may run later; schedule and actual timestamps remain explicit',
                      'Failed, timed-out and blocked trials are retained and never automatically retried']}
    if args.recover_unexecuted:
        recover_unexecuted(result)
    done = {row['key'] for row in result['reports']}
    selected = set(args.tasks.split(',')) if args.tasks else set(all_tasks())
    pending = [row for row in result['schedule'] if row['condition'] in conditions and row['task'] in selected and row['key'] not in done]
    if args.limit:
        pending = pending[:args.limit]
    result.update(runnerPid=os.getpid(), selectedConditions=conditions, workers=args.workers,
                  oracleFreeze=oracle)
    save_report(args.output, result)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        active = {}
        while pending or active:
            while pending and len(active) < args.workers:
                item = pending.pop(0)
                item = {**item, 'attemptNumber': result.get('attemptNumbers', {}).get(item['key'], 1)}
                print('START ' + item['key'], flush=True)
                future = pool.submit(trial, root, item, configurations[item['condition']], model, args.timeout)
                active[future] = item
            finished, _ = wait(active, timeout=30, return_when=FIRST_COMPLETED)
            for future in finished:
                item = active.pop(future)
                try:
                    row = future.result()
                except Exception as exc:
                    row = {**item, 'outcome': {'passed': False, 'checks': 0, 'evaluationBlocked': True},
                           'turnStatus': 'runner-error', 'error': str(exc), 'wallSeconds': 0,
                           'eligibleForComparison': False}
                result['reports'].append(row)
                if row.get('environmentBlocked'):
                    result['pausedForEnvironment'] = True
                    result['pauseReason'] = row.get('error') or row['outcome'].get('error')
                    pending.clear()  # Drain active calls; schedule retains every unstarted trial for resume.
                result['totals'] = totals(result['reports'])
                result['activeKeys'] = [value['key'] for value in active.values()]
                save_report(args.output, result)
                print(json.dumps({'key': item['key'], 'passed': row['outcome']['passed'],
                                  'wallSeconds': row['wallSeconds'], 'totals': result['totals']}), flush=True)
    result['activeKeys'] = []
    result['complete'] = len(result['reports']) == len(result['schedule'])
    save_report(args.output, result)


if __name__ == '__main__':
    main()
