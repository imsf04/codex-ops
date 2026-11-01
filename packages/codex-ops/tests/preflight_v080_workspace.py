"""Prove ordinary PowerShell cwd and audit/oracle isolation before paid trials."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import files
from preflight_v080_profiles import PRIVATE, profile
from v080_native_host import NativeHost

MARKER = 'V080_HARNESS_AUDIT_SENTINEL_735184'


def inventory(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def main():
    run_id = str(time.time_ns())
    workspace = Path('C:/Temp/CodexOpsAcceptance-v080')/('isolation-'+run_id)
    workspace.mkdir(parents=True)
    workspace = workspace.resolve()
    (workspace/'source.py').write_text('def clamp(value):\n    return min(value, 7)\n',encoding='utf-8')
    before = inventory(workspace)
    area = PRIVATE/('isolation-'+run_id)
    store = area/'store'
    store.mkdir(parents=True)
    oracle = area/'expected-answer.json'
    oracle.write_text(json.dumps({'marker':MARKER,'answer':7}),encoding='utf-8')
    os.environ['CODEX_OPS_STORE'] = str(store)
    os.environ['CODEX_OPS_MEASUREMENT_ORIGIN'] = 'validation'
    host = NativeHost(profile('0.8.0'),workspace,store)
    try:
        host.open(workspace)
        host.rpc_stream.write(json.dumps({'auditMarker':MARKER})+'\n')
        host.rpc_stream.flush()
        result = host.request('command/exec',{
            'command':['C:/Program Files/PowerShell/7/pwsh.exe','-NoProfile','-NonInteractive','-Command','(Get-Location).Path'],
            'cwd':str(workspace),'timeoutMs':15000},timeout=30)
        assert result['exitCode']==0, result
        observed = Path(result['stdout'].strip()).resolve()
        assert observed==workspace, (str(observed),str(workspace))
        search = files.run(str(workspace),'search',{'path':'.','pattern':MARKER,'maxMatches':8,'maxFiles':3})
        assert search['status']=='completed' and not search.get('matches'), search
        artifacts = [host.rpc_path,host.events_path,host.stderr_path,oracle,store,ROOT/'tests/native_v080_oracle.py']
        assert all(not path.resolve().is_relative_to(workspace) for path in artifacts)
        assert inventory(workspace)==before
        receipt = {'paidModelCalls':0,'workspace':str(workspace),'actualPowerShellCwd':str(observed),
                   'fixtureInventoryUnchanged':True,'artifactPaths':[str(path) for path in artifacts],
                   'allArtifactsOutsideWorkspace':True,'rustSearchDidNotFindAuditOrOracleMarker':True,
                   'scope':'Artifacts are outside task files/search root, not a claim that workspace-write denies every external read.'}
    finally:
        host.close()
    destination = ROOT/'verification/v080-workspace-isolation.json'
    destination.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':
    main()
