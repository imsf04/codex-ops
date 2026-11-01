"""Paired real-model repair pilot through native app-server, opt-in with --run."""
import argparse
from collections import Counter
import inspect
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
    def __init__(self, executable, workspace, store):
        env = {**os.environ, 'CODEX_OPS_STORE': str(store), 'CODEX_OPS_MEASUREMENT_ORIGIN': 'validation'}
        for name in ('CODEX_APP_TOOLS_PIPE_PATH', 'BROWSER_USE_PIPE_PATH', 'BROWSER_USE_ACCESS_PIPE_PATH',
                     'BROWSER_USE_ACCESS_EXECUTOR_ID', 'CODEX_OPS_AUTO_OUTPUT',
                     'CODEX_OPS_BRIDGE_MANAGER_PID', 'CODEX_OPS_BRIDGE_SHIM_PID'):
            env.pop(name, None)
        self.stderr_path = workspace / 'host.stderr.log'
        self.stderr_stream = self.stderr_path.open('w', encoding='utf-8')
        self.process = subprocess.Popen([str(executable), *flags(), 'app-server', '--stdio'],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.stderr_stream, text=True, encoding='utf-8', env=env,
                                        cwd=workspace, creationflags=subprocess.CREATE_NO_WINDOW)
        self.inbox = queue.Queue()
        self.next_id = 0
        self.tokens = None
        self.items = Counter()
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
        if message.get('method') == 'thread/tokenUsage/updated':
            self.tokens = params.get('tokenUsage')
        if message.get('method') == 'item/completed':
            self.items[params.get('item', {}).get('type', 'unknown')] += 1
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

    def run(self, workspace, model, timeout):
        self.request('initialize', {'clientInfo': {'name': 'codex-ops-real-model-benchmark', 'version': '0.4.0'},
                                    'capabilities': {'experimentalApi': True}})
        self.send({'method': 'initialized'})
        params = {'cwd': str(workspace), 'ephemeral': True, 'sandbox': 'workspace-write', 'approvalPolicy': 'never'}
        if model:
            params['model'] = model
        started = self.request('thread/start', params)
        self.thread = started['thread']['id']
        self.request('turn/start', {'threadId': self.thread,
                                   'input': [{'type': 'text', 'text': SPEC}]})
        deadline = time.monotonic() + timeout
        while self.turn is None and time.monotonic() < deadline:
            self.receive(max(0.1, deadline - time.monotonic()))
        if self.turn is None:
            raise TimeoutError('Repair turn did not complete')
        return {'model': started.get('model'), 'turnStatus': self.turn['status'],
                'turnError': self.turn.get('error'), 'tokens': self.tokens,
                'completedItemsByType': dict(self.items)}

    def close(self):
        self.process.terminate()
        self.process.wait(timeout=10)
        self.stderr_stream.close()


def trial(root, label, executable, model, timeout):
    workspace = root / label
    prepare(workspace)
    before = evaluate(workspace)
    assert not before['passed'], 'Fixture must fail before the model repair'
    store = root / (label + '-store')
    started = time.monotonic()
    host = Host(executable, workspace, store)
    try:
        report = host.run(workspace, model, timeout)
    except (OSError, RuntimeError, TimeoutError, queue.Empty) as exc:
        report = {'turnStatus': 'incomplete', 'error': str(exc), 'tokens': host.tokens,
                  'completedItemsByType': dict(host.items)}
    finally:
        host.close()
    report.update(label=label, workspace=str(workspace), wallSeconds=round(time.monotonic() - started, 3),
                  before=before, outcome=evaluate(workspace), stderrPath=str(host.stderr_path))
    sys.path.insert(0, str(PACKAGE))
    from telemetry import snapshot
    report['presentation'] = snapshot('validation', store)
    observed = report['presentation'].get('totals', {}).get('items', 0) > 0
    report['bridgeObserved'] = observed
    report['treatmentValid'] = observed == label.endswith('-enabled')
    diagnostics = host.stderr_path.read_text(encoding='utf-8')
    blocked = 'orchestrator_helper_launch_canceled' in diagnostics
    report['environmentBlocked'] = blocked
    report['environmentBlockReason'] = 'Windows sandbox setup helper was cancelled; no permission fallback used' if blocked else None
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Execute real model calls using installed Codex authentication')
    parser.add_argument('--self-test', action='store_true', help='Validate the repair fixture without model calls')
    parser.add_argument('--shim', type=Path)
    parser.add_argument('--model')
    parser.add_argument('--pairs', type=int, choices=range(1, 6), default=1)
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    if args.self_test:
        with tempfile.TemporaryDirectory(prefix='codex-ops-model-fixture-') as directory:
            root = Path(directory) / 'fixture'
            prepare(root)
            assert not evaluate(root)['passed']
            (root / 'ledger.py').write_text(inspect.getsource(oracle).replace('def oracle(', 'def summarize('), encoding='utf-8')
            result = evaluate(root)
            assert result['passed'], result
            print(json.dumps({'externalModelCalls': False, 'fixtureSelfTest': result}))
        return
    if not args.run:
        print(json.dumps({'status': 'not-run', 'requires': '--run --shim <validated 0.4 staged shim>',
                          'scope': 'paired controlled repair task, real model usage and independent outcome checks'}))
        return
    if args.shim is None or not args.shim.is_file():
        parser.error('--run requires an existing validated --shim executable')
    root = Path(tempfile.mkdtemp(prefix='codex-ops-model-benchmark-'))
    reports = []
    for pair in range(args.pairs):
        choices = [('baseline', native_cli()), ('enabled', args.shim)]
        if pair % 2:
            choices.reverse()
        for label, executable in choices:
            print(f'START pair {pair + 1} {label}', flush=True)
            report = trial(root, f'{pair + 1}-{label}', executable, args.model, args.timeout)
            reports.append(report)
            print(json.dumps({'label': report['label'], 'outcome': report['outcome'],
                              'turnStatus': report['turnStatus'], 'wallSeconds': report['wallSeconds']}), flush=True)
    result = {'type': 'controlled-repair-real-model-pilot', 'externalModelCalls': True, 'root': str(root),
              'pairs': args.pairs, 'reports': reports,
              'eligibleForComparison': all(row.get('treatmentValid') and not row.get('environmentBlocked')
                                           and row.get('tokens') and row['turnStatus'] == 'completed' for row in reports),
              'limitations': ['One controlled repair task, not representative daily-work or broad quality evidence.',
                              'Model nondeterminism, caching and run order affect token and time comparisons.',
                              'Completed item counts follow native event types; they are not inferred model request counts.',
                              'No output compression or token reduction is assumed; zero and negative gains are retained.']}
    output = PACKAGE / 'verification/real-model-benchmark.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(output))


if __name__ == '__main__':
    main()
