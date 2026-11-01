"""Opt-in raw app-server events using the existing free localhost model fixture.

The frozen probe source is transformed only in memory. Neither production nor
the benchmark harness is modified; model traffic goes to its localhost fixture.
"""
import argparse
from collections import Counter
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import re
import sys


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--receipt',type=Path,required=True)
    args,probe_args=parser.parse_known_args()
    assert not args.receipt.exists(),'Keep prior probe receipts'
    probe=Path(__file__).with_name('probe_app_server.py')
    original=probe.read_bytes();source=original.decode('utf-8')
    old="'ephemeral': True})"
    assert source.count(old)==1,'Review changed probe before inserting opt-in'
    source=source.replace(old,"'ephemeral': True, 'experimentalRawEvents': True})",1)
    sys.argv=[str(probe),*probe_args]
    stdout=io.StringIO()
    with redirect_stdout(stdout):
        exec(compile(source,str(probe),'exec'),{'__name__':'__main__','__file__':str(probe)})
    assert probe.read_bytes()==original,'Frozen probe changed'
    result=json.loads(stdout.getvalue().splitlines()[-1]);root=Path(result['root'])
    events=json.loads((root/'events.json').read_text(encoding='utf-8'))
    raw=[e['params'] for e in events if e.get('method')=='rawResponseItem/completed']
    items=[e['item'] for e in raw]
    calls={i['call_id']:i for i in items if i.get('type') in ('custom_tool_call','function_call')}
    outputs=[i for i in items if i.get('type') in ('custom_tool_call_output','function_call_output')]
    delivered=[]
    for path in root.glob('model-request-*.json'):
        request=json.loads(path.read_text(encoding='utf-8'))
        delivered.extend(i for i in request.get('input',[]) if i.get('type','').endswith('_output'))
    comparisons=[{'callId':i.get('call_id'),'type':i['type'],
                  'matchesModelRequestOutput':any(i.get('call_id')==j.get('call_id') and canonical(i.get('output'))==canonical(j.get('output')) for j in delivered),
                  'references':list(dict.fromkeys(re.findall(r'ops://[a-f0-9]{48}',canonical(i.get('output')))))} for i in outputs]
    receipt={'paidModelCalls':0,'provider':'deterministic localhost HTTP fixture',
             'sourceProbe':str(probe),'sourceSha256':hashlib.sha256(original).hexdigest(),
             'onlyChange':'thread/start.experimentalRawEvents=true in memory',
             'nativeProbe':result,'rawNotificationCount':len(raw),'itemTypes':dict(Counter(i.get('type') for i in items)),
             'outerCalls':[{'callId':key,'type':i['type'],'name':i.get('name'),'namespace':i.get('namespace')} for key,i in calls.items()],
             'outerExecCount':sum(i.get('name')=='exec' for i in calls.values()),
             'outerWaitCount':sum(i.get('name')=='wait' for i in calls.values()),'outputComparisons':comparisons,
             'limitations':['Experimental internal-use protocol; behavior must remain version-tested.',
                'Deterministic local fixture is protocol evidence, not paid-model cost or task-quality evidence.',
                'Current already-running frozen benchmark does not retroactively gain these events.']}
    args.receipt.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
