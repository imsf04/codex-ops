"""Explicitly restore the original desktop sandbox after all model runs finish."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import queue
import time
import tomllib
import uuid

from native_cli import native_cli, mcp_python
from run_model_benchmark import Host
from v080_native_host import codex_home

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_HOME = Path.home() / '.codex'


def inputs(home):
    return {name: hashlib.sha256((home / name).read_bytes()).hexdigest()
            for name in ('config.toml', 'auth.json') if (home / name).is_file()}


class SandboxHost(Host):
    def __init__(self, home, workspace, store):
        self.setup_events = []
        with codex_home(home):
            super().__init__(native_cli(), workspace, store,
                             ['-c', 'windows.sandbox="elevated"'], artifact_prefix='restore-')

    def receive(self, timeout):
        message = super().receive(timeout)
        if str(message.get('method', '')).startswith('windowsSandbox/'):
            self.setup_events.append(message)
        return message


def completion(host):
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        completed = next((event for event in host.setup_events
                          if event.get('method') == 'windowsSandbox/setupCompleted'), None)
        if completed is not None:
            return completed
        try:
            host.receive(10)
        except queue.Empty:
            print(json.dumps({'waitingForOfficialSetup': True}), flush=True)
    raise TimeoutError('Official Windows sandbox setup did not complete within 240 seconds')


def native_command(host, workspace):
    policy = {'type': 'workspaceWrite', 'writableRoots': [str(workspace)], 'networkAccess': False,
              'excludeTmpdirEnvVar': True, 'excludeSlashTmp': True}
    command = [str(mcp_python()), '-I', '-c', 'import os; print(os.getcwd())']
    result = host.request('command/exec', {'command': command,
                          'cwd': str(workspace), 'timeoutMs': 15000, 'sandboxPolicy': policy}, timeout=45)
    assert result['exitCode'] == 0, result
    observed = result['stdout'].strip().splitlines()[-1]
    assert Path(observed).samefile(workspace), result
    return {'command': command, 'result': result, 'sandboxPolicy': policy, 'cwdSameFile': True}


def restore(verify_only=False, prior_receipt=None):
    home = ORIGINAL_HOME
    config = tomllib.loads((home / 'config.toml').read_text(encoding='utf-8'))
    assert config.get('windows', {}).get('sandbox') == 'elevated', 'Refusing to change the original desktop sandbox mode'
    original = inputs(home)
    prior = None
    if verify_only:
        prior_bytes = prior_receipt.read_bytes()
        prior = json.loads(prior_bytes)
        assert Path(prior['home']).samefile(home)
        assert prior['completed']['params']['success'] and prior['after']['status'] == 'ready'
        assert prior['configAuthUnchanged'], 'Prior official restoration changed config/auth'
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')
    receipt_root = ROOT / 'verification/desktop-sandbox-restore' / stamp
    receipt_root.mkdir(parents=True, exist_ok=False)
    workspace = Path('C:/Temp/CodexOpsAcceptance-v080') / ('desktop-restore-' + uuid.uuid4().hex)
    workspace.mkdir(parents=True, exist_ok=False)
    workspace = workspace.resolve()
    record = {'home': str(home), 'workspace': str(workspace), 'paidModelCalls': 0,
              'officialLifecycleOnly': True, 'mode': 'elevated', 'operatorConfirmedBenchmarksStopped': True,
              'verifyOnly': verify_only, 'setupInvoked': False, 'configAuthBeforeSha256': original}
    if verify_only:
        record['officialSetupEvidence'] = {'path': str(prior_receipt),
                                          'sha256': hashlib.sha256(prior_bytes).hexdigest(),
                                          'completed': prior['completed'], 'readiness': prior['after']}
    host = SandboxHost(home, workspace, receipt_root / 'store')
    try:
        host.request('initialize', {'clientInfo': {'name': 'codex-ops-desktop-sandbox-restore', 'version': '0.8.0'},
                                    'capabilities': {'experimentalApi': True}})
        host.send({'method': 'initialized'})
        record['before'] = host.request('windowsSandbox/readiness', None)
        if not verify_only:
            record['setupInvoked'] = True
            record['started'] = host.request('windowsSandbox/setupStart', {'mode': 'elevated', 'cwd': str(workspace)})
            print(json.dumps({'officialSetupStarted': record['started']}), flush=True)
            record['completed'] = completion(host)
            assert record['completed']['params']['success'], record['completed']
        record['after'] = host.request('windowsSandbox/readiness', None)
        assert record['after']['status'] == 'ready', record['after']
        record['nativeProbe'] = native_command(host, workspace)
        record['passed'] = True
    except Exception as exc:
        record['passed'] = False
        record['error'] = repr(exc)
        raise
    finally:
        host.close()
        record['configAuthUnchanged'] = inputs(home) == original
        record['configAuthAfterSha256'] = inputs(home)
        record['events'] = host.setup_events
        (receipt_root / 'report.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        assert record['configAuthUnchanged'], 'Official setup changed config/auth; inspect saved receipt before continuing'
    (ROOT / 'verification/v080-desktop-sandbox-restored.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps({'passed': record['passed'], 'home': str(home), 'configAuthUnchanged': True,
                      'receipt': str(receipt_root / 'report.json')}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--verify-only', action='store_true', help='Never invoke setup; verify prior successful official restoration')
    parser.add_argument('--prior-receipt', type=Path, help='Required with --verify-only; bind the prior official setup success')
    parser.add_argument('--benchmarks-stopped', action='store_true', help='Required confirmation from the coordinating harness owner')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'preparedOnly': True, 'home': str(ORIGINAL_HOME),
                          'requires': '--execute --benchmarks-stopped after every model/native benchmark process has ended'}))
        return
    if not args.benchmarks_stopped:
        parser.error('Do not rotate shared sandbox accounts while benchmarks are running')
    if args.verify_only and not args.prior_receipt:
        parser.error('--verify-only requires --prior-receipt')
    restore(args.verify_only, args.prior_receipt)


if __name__ == '__main__':
    main()
