"""Five controlled real-model tasks through native app-server; opt-in with --run."""
import argparse
import base64
from collections import Counter
import inspect
import hashlib
import json
import os
from pathlib import Path
import queue
import random
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import uuid

from native_cli import native_cli

PACKAGE = Path(__file__).resolve().parents[1]
BROKEN = '''def summarize(events):
    latest = {}
    for event in events:
        latest.setdefault(event["order_id"], event)
    totals = {}
    for event in latest.values():
        if event["status"] != "cancelled":
            row = totals.setdefault(event["region"], {"orders": 0, "total_cents": 0})
            row["orders"] += 1
            row["total_cents"] += event["amount_cents"]
    return dict(sorted(totals.items()))
'''
SPEC = '''Repair the order-ledger summary in ledger.py and verify it with tests.
Events can arrive out of order. For each order_id use the highest integer revision;
if revisions tie, the event appearing last in the input wins. Count only orders
whose selected event has status "paid". Pending, cancelled and refunded orders
contribute nothing. Group by the selected region, preserve exact integer cents,
and return region keys in sorted order. A paid zero-value order still counts.
The input events and their dictionaries must remain unchanged.
orders.json is a representative event stream. test_ledger.py contains initial
regressions; you may add focused tests. Work only in this fixture workspace, with
no downloads or network requests. Finish by running the tests and reporting the fix.
'''
PUBLIC_TEST = '''import unittest
from ledger import summarize

def event(revision, status, amount, region="SG"):
    return dict(order_id="A", revision=revision, status=status, amount_cents=amount, region=region)

class LedgerTests(unittest.TestCase):
    def test_late_old_event(self):
        events = [event(2, "paid", 200), event(3, "cancelled", 200), event(1, "paid", 100)]
        self.assertEqual(summarize(events), {})

    def test_equal_revision_last_event_wins(self):
        self.assertEqual(summarize([event(1, "paid", 90), event(1, "paid", 120)]),
                         {"SG": {"orders": 1, "total_cents": 120}})

    def test_pending_is_not_revenue(self):
        self.assertEqual(summarize([event(1, "pending", 90)]), {})

if __name__ == "__main__":
    unittest.main()
'''
EVALUATE = '''import copy, importlib.util, json, sys
from pathlib import Path
root = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("fixture_ledger", root / "ledger.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
cases = json.load(sys.stdin)
failed = []
for index, case in enumerate(cases):
    events = copy.deepcopy(case["events"])
    try:
        actual = module.summarize(events)
        correct = actual == case["expected"] and list(actual) == sorted(actual)
        correct = correct and events == case["events"]
        if not correct: failed.append({"case": index, "reason": "result, ordering or input mutation"})
    except Exception as exc:
        failed.append({"case": index, "reason": type(exc).__name__})
print(json.dumps({"passed": not failed, "checks": len(cases), "failures": failed}))
'''


def oracle(events):
    selected = {}
    for index, item in sorted(enumerate(events), key=lambda pair: (pair[1]['revision'], pair[0])):
        selected[item['order_id']] = item
    result = {}
    for item in selected.values():
        if item['status'] == 'paid':
            row = result.setdefault(item['region'], {'orders': 0, 'total_cents': 0})
            row['orders'] += 1
            row['total_cents'] += item['amount_cents']
    return dict(sorted(result.items()))


def event_stream():
    rng = random.Random(404)
    return [{'order_id': f'O{index % 400:04}', 'revision': index // 400,
             'status': rng.choice(['paid', 'paid', 'pending', 'cancelled', 'refunded']),
             'amount_cents': rng.randrange(0, 100000), 'region': rng.choice(['SG', 'CN', 'US'])}
            for index in range(1200)]


def cases():
    stream = event_stream()
    variants = [[], stream, list(reversed(stream)), stream[100:300], stream[::7]]
    large = {'order_id': 'large', 'revision': 1, 'status': 'paid',
             'amount_cents': 10 ** 18 + 1, 'region': 'Z'}
    variants.extend([[large], [large, {**large, 'amount_cents': 0}],
                     [large, {**large, 'revision': 2, 'status': 'refunded'}]])
    return [{'events': value, 'expected': oracle(value)} for value in variants]


def prepare(root):
    root.mkdir(parents=True)
    for name, value in [('ledger.py', BROKEN), ('test_ledger.py', PUBLIC_TEST), ('README.md', SPEC)]:
        (root / name).write_text(value, encoding='utf-8')
    (root / 'orders.json').write_text(json.dumps(event_stream(), indent=2), encoding='utf-8')


def evaluate(root):
    result = subprocess.run([sys.executable, '-I', '-c', EVALUATE, str(root)],
                            input=json.dumps(cases()), capture_output=True, text=True, timeout=30)
    if result.returncode:
        return {'passed': False, 'checks': 0, 'error': result.stderr[-1500:]}
    return json.loads(result.stdout)


def flags():
    values = ['features.code_mode=true', 'features.code_mode_only=true',
              'features.code_mode_host=true', 'features.plugins=false', 'features.apps=false',
              'features.multi_agent=false', 'web_search="disabled"']
    home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    config = home / 'config.toml'
    if config.exists():
        settings = tomllib.loads(config.read_text(encoding='utf-8'))
        names = list(settings.get('mcp_servers', {}))
        if any(not name.replace('_', '').replace('-', '').isalnum() for name in names):
            raise ValueError('Benchmark MCP names must be simple CLI key segments')
        values += [f'mcp_servers.{name}.enabled=false' for name in names]
    return [arg for value in values for arg in ('-c', value)]


class Host:
    def __init__(self, executable, workspace, store, extra_flags=None, artifact_prefix=''):
        env = {**os.environ, 'CODEX_OPS_STORE': str(store), 'CODEX_OPS_MEASUREMENT_ORIGIN': 'validation'}
        for name in ('CODEX_APP_TOOLS_PIPE_PATH', 'BROWSER_USE_PIPE_PATH', 'BROWSER_USE_ACCESS_PIPE_PATH',
                     'BROWSER_USE_ACCESS_EXECUTOR_ID', 'CODEX_OPS_AUTO_OUTPUT',
                     'CODEX_OPS_BRIDGE_MANAGER_PID', 'CODEX_OPS_BRIDGE_SHIM_PID'):
            env.pop(name, None)
        self.stderr_path = workspace / (artifact_prefix + 'host.stderr.log')
        self.stderr_stream = self.stderr_path.open('w', encoding='utf-8')
        self.events_path = workspace.parent / (artifact_prefix + workspace.name + '.events.jsonl')
        self.events_stream = self.events_path.open('w', encoding='utf-8')
        self.process = subprocess.Popen([str(executable), *flags(), *(extra_flags or []), 'app-server', '--stdio'],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.stderr_stream, text=True, encoding='utf-8', env=env,
                                        cwd=workspace, creationflags=subprocess.CREATE_NO_WINDOW)
        self.inbox = queue.Queue()
        self.next_id = 0
        self.tokens = None
        self.items = Counter()
        self.tools = Counter()
        self.methods = Counter()
        self.agent_messages = []
        self.candidate_tools = None
        self.has_candidate = bool(extra_flags)
        self.turn = None
        self.thread = None
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.process.stdout:
            try:
                self.inbox.put(json.loads(line))
            except ValueError:
                pass
        self.inbox.put({'transportClosed': True})

    def send(self, value):
        self.process.stdin.write(json.dumps(value) + '\n')
        self.process.stdin.flush()

    def receive(self, timeout):
        message = self.inbox.get(timeout=timeout)
        if message.get('transportClosed'):
            raise RuntimeError('Native app-server closed before completion')
        params = message.get('params', {})
        if message.get('method'):
            self.methods[message['method']] += 1
        if message.get('method') in ('item/completed', 'turn/completed', 'thread/tokenUsage/updated'):
            self.events_stream.write(json.dumps(message, ensure_ascii=False) + '\n')
            self.events_stream.flush()
        if message.get('method') == 'thread/tokenUsage/updated':
            self.tokens = params.get('tokenUsage')
        if message.get('method') == 'item/completed':
            item = params.get('item', {})
            self.items[item.get('type', 'unknown')] += 1
            if item.get('type') == 'mcpToolCall':
                self.tools[str(item.get('server')) + '.' + str(item.get('tool'))] += 1
            if item.get('type') == 'agentMessage':
                self.agent_messages.append({'phase': item.get('phase'), 'text': item.get('text', '')[:12000]})
        if message.get('method') == 'turn/completed':
            self.turn = params['turn']
        return message

    def request(self, method, params, timeout=60):
        self.next_id += 1
        request_id = self.next_id
        self.send({'id': request_id, 'method': method, 'params': params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.receive(max(0.1, deadline - time.monotonic()))
            if message.get('id') == request_id:
                if 'error' in message:
                    raise RuntimeError(json.dumps(message['error']))
                return message['result']
        raise TimeoutError(method)

    def run(self, workspace, model, timeout, spec=SPEC, instructions=None, expected_tool_count=6):
        self.request('initialize', {'clientInfo': {'name': 'codex-ops-real-model-benchmark', 'version': '0.5.0'},
                                    'capabilities': {'experimentalApi': True}})
        self.send({'method': 'initialized'})
        readiness = self.request('windowsSandbox/readiness', None)
        if readiness.get('status') != 'ready':
            raise RuntimeError('Native sandbox is not ready: ' + json.dumps(readiness))
        if self.has_candidate:
            status = self.request('mcpServerStatus/list', {'serverName': 'ops_bench', 'detail': 'toolsAndAuthOnly'})
            server = status['data'][0]
            if server.get('toolsError') or len(server.get('tools', {})) != expected_tool_count:
                raise RuntimeError('Candidate MCP catalogue is not ready: ' + str(server.get('toolsError')))
            self.candidate_tools = list(server['tools'])
        params = {'cwd': str(workspace), 'ephemeral': True, 'sandbox': 'workspace-write', 'approvalPolicy': 'never'}
        if instructions:
            params['developerInstructions'] = instructions
        if model:
            params['model'] = model
        started = self.request('thread/start', params)
        self.thread = started['thread']['id']
        self.request('turn/start', {'threadId': self.thread,
                                   'input': [{'type': 'text', 'text': spec}]})
        deadline = time.monotonic() + timeout
        while self.turn is None and time.monotonic() < deadline:
            self.receive(max(0.1, deadline - time.monotonic()))
        if self.turn is None:
            raise TimeoutError('Repair turn did not complete')
        return {'model': started.get('model'), 'turnStatus': self.turn['status'],
                'turnError': self.turn.get('error'), 'tokens': self.tokens,
                'completedItemsByType': dict(self.items), 'completedMcpTools': dict(self.tools),
                'nativeMethodsObserved': dict(self.methods), 'agentMessages': self.agent_messages,
                'candidateTools': self.candidate_tools}

    def close(self):
        self.process.terminate()
        self.process.wait(timeout=10)
        self.stderr_stream.close()
        self.events_stream.close()
        self.process.stdin.close()
        self.process.stdout.close()



def candidate_flags(store):
    values = [
        'mcp_servers.ops_bench.command=' + json.dumps(sys.executable),
        'mcp_servers.ops_bench.args=' + json.dumps([str(PACKAGE / 'server.py')]),
        'mcp_servers.ops_bench.enabled=true',
        'mcp_servers.ops_bench.startup_timeout_sec=30',
        'mcp_servers.ops_bench.tool_timeout_sec=60',
        'mcp_servers.ops_bench.env.CODEX_OPS_STORE=' + json.dumps(str(store)),
        'mcp_servers.ops_bench.env.CODEX_OPS_MEASUREMENT_ORIGIN="validation"',
    ]
    return [arg for value in values for arg in ('-c', value)]


def native_evaluate(host, task, workspace, expected):
    payload = {key: value for key, value in expected.items() if key != 'spec'}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    command = [str(Path(sys.base_prefix) / 'python.exe'), '-I',
               str(PACKAGE / 'tests/native_model_oracle.py'), '--task', task,
               '--root', str(workspace), '--expected', encoded]
    result = host.request('command/exec', {'command': command, 'cwd': str(workspace), 'timeoutMs': 30000}, timeout=45)
    if result['exitCode']:
        return {'passed': False, 'checks': 0, 'evaluationBlocked': True, 'error': result['stderr'][-2000:]}
    return {**json.loads(result['stdout']), 'evaluationSandbox': 'native configured workspace-write'}


def trial(root, task, condition, executable, model, timeout, started_callback=None):
    from model_tasks import prepare_task, evaluate_task
    workspace = root / condition / task
    expected = prepare_task(task, workspace)
    before = evaluate_task(task, workspace, expected)
    assert not before['passed'], 'Fixture must require work before model execution'
    store = Path.home() / 'AppData/Local/CodexOps/verification/model-v05' / root.name / task
    store.mkdir(parents=True, exist_ok=True)
    sources = [*PACKAGE.glob('*.py'), *(PACKAGE / 'mutations').glob('*.py'), *(PACKAGE / 'runtime_bridge').glob('*.py')]
    source_hashes = {str(path.relative_to(PACKAGE)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in sources} if condition == 'enabled' else {}
    extra = candidate_flags(store) if condition == 'enabled' else []
    started = time.monotonic()
    host = Host(executable, workspace, store, extra)
    if started_callback:
        started_callback(host.process.pid, task)
    outcome = None
    try:
        report = host.run(workspace, model, timeout, expected['spec'])
    except (OSError, RuntimeError, TimeoutError, queue.Empty) as exc:
        report = {'turnStatus': 'incomplete', 'error': str(exc), 'tokens': host.tokens,
                  'completedItemsByType': dict(host.items), 'completedMcpTools': dict(host.tools),
                  'nativeMethodsObserved': dict(host.methods), 'agentMessages': host.agent_messages,
                  'candidateTools': host.candidate_tools}
    wall_seconds = round(time.monotonic() - started, 3)
    try:
        outcome = native_evaluate(host, task, workspace, expected)
    except (OSError, RuntimeError, TimeoutError, queue.Empty, ValueError) as exc:
        outcome = {'passed': False, 'checks': 0, 'evaluationBlocked': True, 'error': str(exc)}
    finally:
        host.close()
    report.update(task=task, condition=condition, workspace=str(workspace),
                  wallSeconds=wall_seconds, before=before, outcome=outcome, stderrPath=str(host.stderr_path),
                  eventsPath=str(host.events_path), candidateSourceSha256=source_hashes,
                  storeRoot=str(store), cacheLayout='ordinary-permission AppData Local CodexOps verification directory',
                  workspaceLayout='ordinary Path.mkdir temporary root')
    sys.path.insert(0, str(PACKAGE))
    from telemetry import snapshot
    report['presentation'] = snapshot('validation', store)
    observed = report['presentation'].get('totals', {}).get('items', 0) > 0
    report['bridgeObserved'] = observed
    report['treatmentValid'] = observed == (condition == 'enabled')
    diagnostics = host.stderr_path.read_text(encoding='utf-8')
    blocked = 'orchestrator_helper_launch_canceled' in diagnostics
    report['environmentBlocked'] = blocked
    report['environmentBlockReason'] = 'Windows sandbox setup helper was cancelled; no permission fallback used' if blocked else None
    report['eligibleForComparison'] = bool(report['treatmentValid'] and not blocked and not outcome.get('evaluationBlocked') and report.get('tokens')
                                          and report['turnStatus'] == 'completed')
    return report


def self_test():
    from model_tasks import TASKS, prepare_task, evaluate_task, solve_for_self_test
    from unittest.mock import patch
    results = []
    with tempfile.TemporaryDirectory(prefix='codex-ops-model-fixtures-') as directory:
        for task in TASKS:
            root = Path(directory) / task
            expected = prepare_task(task, root)
            assert not evaluate_task(task, root, expected)['passed'], task
            solve_for_self_test(task, root, expected)
            result = evaluate_task(task, root, expected)
            assert result['passed'], (task, result)
            results.append({'task': task, **result})
        root = Path(directory) / 'oracle-negative-checks'
        expected = prepare_task('batch_changes', root)
        solve_for_self_test('batch_changes', root, expected)
        target = root / 'docs/migration.txt'
        target.unlink()
        target.mkdir()
        assert not evaluate_task('batch_changes', root, expected)['passed']
        target.rmdir()
        target.write_bytes(expected['files']['docs/migration.txt'].encode())
        original_read = Path.read_bytes
        for denied in ('migration.txt', 'notes.txt'):
            def unreadable(path):
                if path.name == denied:
                    raise PermissionError('fixture read denied')
                return original_read(path)
            with patch.object(Path, 'read_bytes', unreadable):
                outcome = evaluate_task('batch_changes', root, expected)
                assert not outcome['passed'] and any('unreadable' in row['reason'] for row in outcome['failures'])
    return {'externalModelCalls': False, 'fixtures': results, 'oracleNegativeChecks': 3}


def report_file(condition):
    return PACKAGE / 'verification' / ('real-model-' + condition + '.json')


def save_report(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def run_condition(args, condition, tasks):
    output = report_file(condition)
    previous = json.loads(output.read_text(encoding='utf-8')) if args.resume else None
    if previous and not args.relocate_remaining:
        root = Path(previous['root'])
    else:
        root = Path(tempfile.gettempdir()) / ('codex-ops-model-' + condition + '-regular-' + uuid.uuid4().hex)
        root.mkdir()
    if not root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise ValueError('Benchmark workspace must remain inside the system temp directory')
    result = {'version': '0.5.0', 'type': 'five-controlled-tasks-real-model-pilot',
              'condition': condition, 'externalModelCalls': True, 'root': str(root), 'runnerPid': os.getpid(),
              'selectedTasks': tasks, 'reports': [], 'complete': False, 'eligibleForComparison': False,
              'treatment': 'original native CLI' if condition == 'baseline' else '0.5 staged bridge plus six candidate MCP tools',
              'limitations': ['Controlled fixtures, not representative daily-work or broad quality evidence.',
                              'Model nondeterminism, caching and run order affect token and time comparisons.',
                              'The enabled treatment includes both the runtime bridge and candidate MCP tools.',
                              'Native completed-item counts are event counts, not inferred model request counts.',
                              'Failed outcomes, zero savings and negative gains are retained.']}
    if previous:
        if previous['condition'] != condition or not set(tasks).issubset(previous['selectedTasks']):
            raise ValueError('Resume condition/tasks do not match existing report')
        result = previous
        result.update(runnerPid=os.getpid(), complete=False)
        if args.relocate_remaining:
            result.setdefault('previousWorkspaceRoots', []).append(result['root'])
            result['root'] = str(root)
        result.pop('pausedBeforeTask', None)
        result.pop('pauseReason', None)
        done = {row['task'] for row in result['reports']}
        tasks = [task for task in tasks if task not in done]
    def started(pid, task):
        result.update(activeHostPid=pid, activeTask=task)
        save_report(output, result)
    save_report(output, result)
    executable = native_cli() if condition == 'baseline' else args.shim
    for task in tasks:
        print('START ' + condition + ' ' + task, flush=True)
        report = trial(root, task, condition, executable, args.model, args.timeout, started)
        result['reports'].append(report)
        result['activeTask'] = None
        result['activeHostPid'] = None
        save_report(output, result)
        print(json.dumps({'condition': condition, 'task': task, 'outcome': report['outcome'],
                          'turnStatus': report['turnStatus'], 'wallSeconds': report['wallSeconds'],
                          'environmentBlocked': report['environmentBlocked']}), flush=True)
    result['complete'] = set(result['selectedTasks']) == {row['task'] for row in result['reports']}
    result['eligibleForComparison'] = all(row['eligibleForComparison'] for row in result['reports'])
    save_report(output, result)
    print(str(output), flush=True)


def main():
    from model_tasks import TASKS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Execute real model calls using installed Codex authentication')
    parser.add_argument('--self-test', action='store_true', help='Validate all fixtures without model calls')
    parser.add_argument('--condition', choices=['baseline', 'enabled', 'both'], default='both')
    parser.add_argument('--resume', action='store_true', help='Append only unfinished selected tasks to the existing condition report')
    parser.add_argument('--relocate-remaining', action='store_true', help='Use a new ordinary-permission temporary root for unfinished tasks only')
    parser.add_argument('--tasks', default=','.join(TASKS))
    parser.add_argument('--shim', type=Path)
    parser.add_argument('--model')
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    tasks = args.tasks.split(',')
    if not tasks or len(set(tasks)) != len(tasks) or any(task not in TASKS for task in tasks):
        parser.error('--tasks must select distinct known task names')
    if args.self_test:
        print(json.dumps(self_test()))
        return
    if not args.run:
        print(json.dumps({'status': 'not-run', 'condition': args.condition, 'tasks': tasks,
                          'requires': '--run; enabled additionally requires --shim <validated 0.5 staged shim>',
                          'scope': 'five controlled tasks, actual model usage and independent file/outcome checks'}))
        return
    if args.condition != 'baseline' and (args.shim is None or not args.shim.is_file()):
        parser.error('enabled condition requires an existing validated --shim executable')
    conditions = ('baseline', 'enabled') if args.condition == 'both' else (args.condition,)
    for condition in conditions:
        run_condition(args, condition, tasks)


if __name__ == '__main__':
    main()
