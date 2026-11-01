"""Measure native PowerShell child-status propagation without paid model calls."""
import json
import os
from pathlib import Path
import time

from preflight_v080_profiles import PRIVATE, profile
from v080_native_host import NativeHost
import v080_model_tasks as tasks


def main():
    root = Path(__file__).resolve().parents[1]
    run_id = str(time.time_ns())
    workspace = Path('C:/Temp/CodexOpsAcceptance-v080')/('terminal-protocol-'+run_id)
    workspace.mkdir(parents=True)
    expected = tasks.terminal_failure(workspace)
    store = PRIVATE/('terminal-protocol-'+run_id)/'store'
    store.mkdir(parents=True)
    os.environ['CODEX_OPS_STORE'] = str(store)
    os.environ['CODEX_OPS_MEASUREMENT_ORIGIN'] = 'validation'
    host = NativeHost(profile('0.8.0'),workspace,store)
    observations = []
    try:
        host.open(workspace)
        for command, status in [('python run_terminal.py',1),
                                ('python run_terminal.py; exit $LASTEXITCODE',9)]:
            result = host.request('command/exec',{
                'command':['C:/Program Files/PowerShell/7/pwsh.exe','-NoProfile','-NonInteractive','-Command',command],
                'cwd':str(workspace),'timeoutMs':45000},timeout=60)
            assert result['exitCode'] == status, result
            assert 'ERROR HOLDOUT_FORMAT expected=R7 observed=R6' in result['stdout'], result
            assert (workspace/'terminal.receipt').read_bytes() == b'finished-exit-9\n'
            observations.append({'command':command,'nativeExitCode':result['exitCode'],
                                 'producerReceiptVerified':True,'lateDiagnosticVerified':True})
        events = [{'method':'item/completed','params':{'item':{'type':'commandExecution',
                   'command':'python run_terminal.py','exitCode':1}}}]
        assert tasks.execution_observed(events,expected)
        assert not tasks.execution_exit_observed(events,expected)
        events[0]['params']['item']['exitCode'] = 9
        assert tasks.execution_exit_observed(events,expected)
        receipt = {'paidModelCalls':0,'passed':True,'workspace':str(workspace),
                   'observations':observations,'oracleExpectedExitUnchanged':9,
                   'presenceAndExpectedExitCheckedSeparately':True}
    finally:
        host.close()
    path = root/'verification/v080-terminal-protocol.json'
    assert not path.exists(), 'Preserve previous native receipt'
    path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt),flush=True)


if __name__ == '__main__':
    main()
