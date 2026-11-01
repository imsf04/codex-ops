"""Free deterministic native Host A/B for the observation-only wrapper."""
import http.server
import json
import os
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch

from native_cli import native_cli
from run_model_benchmark import Host
from run_v070_observed import instrument

ROOT=Path(__file__).resolve().parents[1]
SCRIPT='text("OBSERVATION_EQUIVALENCE");'


class Model(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append(body);number=len(self.server.requests)
        item={'type':'custom_tool_call','id':'tc_1','call_id':'call_1','name':'exec','input':SCRIPT} if number==1 else {
            'type':'message','id':'msg_done','role':'assistant','status':'completed',
            'content':[{'type':'output_text','text':'DONE','annotations':[]}]}
        response={'id':f'resp_{number}','object':'response','status':'completed','output':[item],
                  'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2}}
        events=[{'type':'response.created','response':{**response,'status':'in_progress','output':[]}},
                {'type':'response.output_item.added','output_index':0,'item':item},
                {'type':'response.output_item.done','output_index':0,'item':item},
                {'type':'response.completed','response':response}]
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
        for event in events:self.wfile.write(('data: '+json.dumps(event)+'\n\n').encode())
        self.wfile.flush()


def main():
    workspace=Path(tempfile.mkdtemp(prefix='codex-ops-observation-proof-'))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Model)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    values=['model_provider="local_observation_probe"','model_providers.local_observation_probe.name="Free localhost fixture"',
            'model_providers.local_observation_probe.base_url='+json.dumps(f'http://127.0.0.1:{server.server_port}/v1'),
            'model_providers.local_observation_probe.wire_api="responses"','model_providers.local_observation_probe.requires_openai_auth=false']
    flags=[v for entry in values for v in ('-c',entry)]
    ledger={'observedAttempts':{}};records={};requests={}
    def run(name):
        server.requests=[]
        host=Host(native_cli(),workspace,workspace/(name+'-store'),flags,artifact_prefix=name+'-')
        host.has_candidate=False  # Provider config is not an MCP server; this fixture has no MCP.
        try:
            records[name]=host.run(workspace,'gpt-5.4',45,'Run the deterministic local protocol fixture.')
            host.request('command/exec',{'command':[r'C:\Windows\System32\cmd.exe','/c','echo ORACLE_BOUNDARY'],
                                        'cwd':str(workspace),'timeoutMs':10000},timeout=15)
        finally:host.close()
        requests[name]=server.requests
        (workspace/(name+'-model-requests.json')).write_text(json.dumps(server.requests,indent=2),encoding='utf-8')
    try:
        with patch.dict(os.environ,{'CODEX_OPS_BRIDGE_STATUS':str(workspace/'bridge-status')}):
            run('control')
            with instrument(Host,ledger,lambda:None):run('observed')
    finally:server.shutdown()
    assert records['control']['turnStatus']==records['observed']['turnStatus']=='completed'
    def inputs(body):return body.get('input',[])
    first_equal=inputs(requests['control'][0])==inputs(requests['observed'][0])
    outputs={name:[i for i in bodies[-1].get('input',[]) if i.get('type','').endswith('_output')]
             for name,bodies in requests.items()}
    outputs_equal=outputs['control']==outputs['observed']
    print(json.dumps({'workspace':str(workspace),'firstModelInputEqual':first_equal,'finalToolOutputsEqual':outputs_equal}),flush=True)
    state=ledger['observedAttempts'][workspace.name]
    assert state['outerExec']==1 and state['outerWait']==0 and state['mainTurnCompleted']
    result={'paidModelCalls':0,'workspace':str(workspace),'provider':'deterministic localhost fixture',
            'firstModelInputEqual':first_equal,'finalToolOutputsEqual':outputs_equal,
            'controlRequests':len(requests['control']),'observedRequests':len(requests['observed']),
            'controlNativeItems':records['control']['completedItemsByType'],
            'observedNativeItems':records['observed']['completedItemsByType'],'observation':state,
            'oracleBoundary':'A native command/exec ran only after the main turn; it does not inflate outer counts.'}
    destination=ROOT/'verification/v070-observed-wrapper-probe.json'
    assert not destination.exists(),'Keep original proof'
    destination.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
