"""Add native raw-event observation in memory; run the unchanged frozen harness."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
RAW='rawResponseItem/completed'


def thread_start_params(method, params):
    if method=='thread/start':return {**params,'experimentalRawEvents':True}
    return params


def new_state(key, events_path):
    return {'key':key,'eventsPath':str(events_path),'mainThreadId':None,'mainTurnId':None,
            'mainTurnCompleted':False,'rawNotifications':0,'mainRawNotifications':0,
            'excludedAfterMainTurn':0,'excludedOtherTurn':0,'calls':{},'outputs':[],
            'observationAvailable':False,'closed':False}


def observe(state, message):
    method=message.get('method');params=message.get('params',{})
    if method=='turn/started' and state['mainTurnId'] is None:
        state['mainTurnId']=params.get('turn',{}).get('id');state['mainThreadId']=params.get('threadId')
    if method=='turn/completed':
        turn=params.get('turn',{}).get('id')
        if state['mainTurnId'] is None:state['mainTurnId']=turn
        if turn==state['mainTurnId']:state['mainTurnCompleted']=True
    if method!=RAW:return
    state['rawNotifications']+=1
    if state['mainTurnCompleted']:
        state['excludedAfterMainTurn']+=1;return
    turn=params.get('turnId');thread=params.get('threadId')
    if state['mainTurnId'] is None:state['mainTurnId']=turn
    if state['mainThreadId'] is None:state['mainThreadId']=thread
    if (turn,thread)!=(state['mainTurnId'],state['mainThreadId']):
        state['excludedOtherTurn']+=1;return
    state['mainRawNotifications']+=1;state['observationAvailable']=True
    item=params.get('item',{});kind=item.get('type');call=item.get('call_id')
    if kind in ('custom_tool_call','function_call') and call:
        state['calls'].setdefault(call,{'callId':call,'type':kind,'name':item.get('name'),'namespace':item.get('namespace')})
    if kind in ('custom_tool_call_output','function_call_output'):
        output=item.get('output');text=output if isinstance(output,str) else json.dumps(output,ensure_ascii=False,separators=(',',':'))
        state['outputs'].append({'callId':call,'type':kind,'itemId':item.get('id'),
                                'rawOrdinal':state['rawNotifications'],'serializedOutputBytes':len(text.encode()),
                                'references':list(dict.fromkeys(re.findall(r'ops://[a-f0-9]{48}',text)))})


def summary(state):
    result={**state,'calls':list(state['calls'].values())}
    available=state['observationAvailable']
    result.update(outerExec=sum(x.get('name')=='exec' for x in state['calls'].values()) if available else None,
                  outerWait=sum(x.get('name')=='wait' for x in state['calls'].values()) if available else None,
                  outerToolCalls=len(state['calls']) if available else None)
    return result


@contextmanager
def instrument(Host, ledger, save):
    original={name:getattr(Host,name) for name in ('__init__','request','receive','close')}
    def initialize(self, *args, **kwargs):
        original['__init__'](self,*args,**kwargs)
        workspace=args[1] if len(args)>1 else kwargs['workspace']
        self._v070_observation=new_state(Path(workspace).name,self.events_path)
        ledger['observedAttempts'][Path(workspace).name]=summary(self._v070_observation);save()
    def request(self, method, params, *args, **kwargs):
        return original['request'](self,method,thread_start_params(method,params),*args,**kwargs)
    def receive(self, *args, **kwargs):
        message=original['receive'](self,*args,**kwargs)
        if message.get('method')==RAW:
            self.events_stream.write(json.dumps(message,ensure_ascii=False)+'\n');self.events_stream.flush()
        state=self._v070_observation;observe(state,message)
        if message.get('method') in (RAW,'turn/completed'):
            ledger['observedAttempts'][state['key']]=summary(state);save()
        return message
    def close(self, *args, **kwargs):
        try:return original['close'](self,*args,**kwargs)
        finally:
            state=self._v070_observation;state['closed']=True
            ledger['observedAttempts'][state['key']]=summary(state);save()
    for name,function in (('__init__',initialize),('request',request),('receive',receive),('close',close)):
        setattr(Host,name,function)
    try:yield
    finally:
        for name,function in original.items():setattr(Host,name,function)


def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--observation-receipt',type=Path,default=ROOT/'verification/v070-native-observation-sidecar.json')
    options,remaining=parser.parse_known_args()
    import run_v070_costs as frozen
    sys.argv=[str(Path(frozen.__file__)),*remaining]
    if '--run' not in remaining:
        frozen.main();return
    locator=argparse.ArgumentParser(add_help=False)
    locator.add_argument('--report',default='verification/v070-costs-final.json')
    location,_=locator.parse_known_args(remaining);report_path=ROOT/location.report
    existing=json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else None
    assert not options.observation_receipt.exists(),'Retain previous instrumentation receipt; choose a new filename'
    ledger={'instrumentationStartedAt':time.time(),'wrapper':str(Path(__file__).resolve()),
            'wrapperSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'frozenHarnessSha256':hashlib.sha256(Path(frozen.__file__).read_bytes()).hexdigest(),
            'report':str(report_path),'priorReportSha256':hashlib.sha256(report_path.read_bytes()).hexdigest() if existing else None,
            'priorKeysOuterUnavailable':[row['key'] for row in existing['reports']] if existing else [],
            'observedAttempts':{},'policy':'Native thread/start raw-event opt-in and event persistence only; original callbacks, model inputs and controls unchanged.',
            'timingLimit':'Observation adds event serialization/disk I/O; latency across instrumentation boundary is not a clean comparison.',
            'countBoundary':'First main model turn only; raw items after its turn/completed, including oracle activity, are excluded.'}
    def save():
        options.observation_receipt.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        with instrument(frozen.harness.Host,ledger,save):frozen.main()
    finally:
        ledger['instrumentationEndedAt']=time.time();save()


if __name__=='__main__':main()
