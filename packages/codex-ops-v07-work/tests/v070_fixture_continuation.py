"""One explicit producer revision; frozen task/oracle modules remain untouched."""
import hashlib
import v070_model_tasks

REVISION='receipt-lf1'
OLD='Path("execution.receipt").write_text("completed-with-exit-7\\n")'
NEW='Path("execution.receipt").write_bytes(b"completed-with-exit-7\\n")'


def prepare_task(name,root):
    expected=v070_model_tasks.prepare_task(name,root)
    if name!='long_command_failure':return expected
    path=root/'run_probe.py';source=path.read_text(encoding='utf-8')
    assert source.count(OLD)==1,'Review changed frozen producer before applying explicit revision'
    path.write_bytes(source.replace(OLD,NEW,1).encode('utf-8'))
    expected['preserved']['run_probe.py']=hashlib.sha256(path.read_bytes()).hexdigest()
    expected['fixtureRevision']=REVISION
    return expected
