"""Execute both original and revised producers through native sandbox, no model."""
import json
import hashlib
from pathlib import Path
import sys
import tempfile

from native_cli import native_cli
from run_model_benchmark import Host
from v070_fixture_continuation import prepare_task as revised
from v070_model_tasks import prepare_task as original

ROOT=Path(__file__).resolve().parents[1]


def run(workspace,prepare):
    expected=prepare('long_command_failure',workspace)
    host=Host(native_cli(),workspace,workspace/'probe-store')
    try:
        host.request('initialize',{'clientInfo':{'name':'codex-ops-native-producer-proof','version':'0.7.0'},
                                  'capabilities':{'experimentalApi':True}})
        host.send({'method':'initialized'})
        readiness=host.request('windowsSandbox/readiness',None)
        assert readiness['status']=='ready',readiness
        host.request('thread/start',{'cwd':str(workspace),'ephemeral':True,'sandbox':'workspace-write','approvalPolicy':'never'})
        command=[str(Path(sys.base_prefix)/'python.exe'),'-I',str(workspace/'run_probe.py')]
        execution=host.request('command/exec',{'command':command,'cwd':str(workspace),'timeoutMs':15000},timeout=20)
        # Read through the same native sandbox, not a fabricated expected-file helper.
        inspect=host.request('command/exec',{'command':[str(Path(sys.base_prefix)/'python.exe'),'-I','-c',
            'from pathlib import Path; import json; p=Path("execution.receipt"); print(json.dumps({"hex":p.read_bytes().hex(),"cwd":str(Path.cwd())}))'],
            'cwd':str(workspace),'timeoutMs':10000},timeout=15)
        assert inspect['exitCode']==0,inspect
        receipt=json.loads(inspect['stdout'])
        return {'workspace':str(workspace),'execution':execution,'nativeReceipt':receipt,
                'requiredHex':expected['requiredFiles']['execution.receipt'].encode().hex(),
                'producerSha256':hashlib.sha256((workspace/'run_probe.py').read_bytes()).hexdigest(),
                'producerProtectedHashMatches':hashlib.sha256((workspace/'run_probe.py').read_bytes()).hexdigest()==expected['preserved']['run_probe.py']}
    finally:host.close()


def main():
    destination=ROOT/'verification/v070-fixture-lf-native-proof.json'
    assert not destination.exists(),'Retain prior proof'
    base=Path(tempfile.mkdtemp(prefix='codex-ops-fixture-lf-proof-'))
    old=run(base/'original',original);new=run(base/'revised',revised)
    result={'paidModelCalls':0,'original':old,'revised':new,
            'oldProducerViolatesFrozenBytes':old['nativeReceipt']['hex']!=old['requiredHex'],
            'revisedProducerSatisfiesFrozenBytes':new['nativeReceipt']['hex']==new['requiredHex'],
            'scope':'Only producer write_text versus write_bytes; expected bytes and native oracle unchanged.'}
    destination.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    assert old['execution']['exitCode']==new['execution']['exitCode']==7,result
    assert result['oldProducerViolatesFrozenBytes'] and result['revisedProducerSatisfiesFrozenBytes'],result
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
