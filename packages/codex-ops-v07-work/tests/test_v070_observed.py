import io
import json
from pathlib import Path
import unittest

from run_v070_observed import instrument, new_state, observe, summary, thread_start_params


def raw(kind,call='one',name='exec',turn='main'):
    return {'method':'rawResponseItem/completed','params':{'threadId':'thread','turnId':turn,
        'item':{'type':kind,'call_id':call,'name':name,'output':'evidence'}}}


class ObservationTests(unittest.TestCase):
    def test_request_opt_in_does_not_mutate_other_controls(self):
        params={'cwd':'C:/fixture','ephemeral':True,'approvalPolicy':'never'}
        result=thread_start_params('thread/start',params)
        self.assertEqual(result,{**params,'experimentalRawEvents':True})
        self.assertNotIn('experimentalRawEvents',params)
        self.assertIs(thread_start_params('turn/start',params),params)

    def test_scope_and_call_id_dedup_preserve_multiple_outputs_and_exclude_oracle(self):
        state=new_state('task','events')
        observe(state,raw('custom_tool_call'));observe(state,raw('custom_tool_call'))
        observe(state,raw('custom_tool_call_output'));observe(state,raw('custom_tool_call_output'))
        observe(state,raw('function_call',call='wait',name='wait'))
        observe(state,raw('custom_tool_call',call='other',turn='other'))
        observe(state,{'method':'turn/completed','params':{'turn':{'id':'main'}}})
        observe(state,raw('custom_tool_call',call='oracle'))
        result=summary(state)
        self.assertEqual(result['outerExec'],1);self.assertEqual(result['outerWait'],1)
        self.assertEqual(len(result['outputs']),2)
        self.assertEqual(result['excludedAfterMainTurn'],1)
        self.assertEqual(result['excludedOtherTurn'],1)

    def test_unavailable_is_not_zero_and_wrapper_restores_original_callbacks(self):
        self.assertIsNone(summary(new_state('task','events'))['outerExec'])
        class FakeHost:
            def __init__(self,executable,workspace,*args,**kwargs):
                self.events_path=Path('events');self.events_stream=io.StringIO();self.next=raw('custom_tool_call')
            def request(self,method,params,*args,**kwargs):return params
            def receive(self,*args,**kwargs):return self.next
            def close(self):return 'native-close'
        original=FakeHost.receive;ledger={'observedAttempts':{}};saved=[]
        with instrument(FakeHost,ledger,lambda:saved.append(True)):
            host=FakeHost('exe',Path('task'))
            self.assertTrue(host.request('thread/start',{})['experimentalRawEvents'])
            self.assertIs(host.receive(),host.next)
            self.assertEqual(json.loads(host.events_stream.getvalue()),host.next)
            self.assertEqual(host.close(),'native-close')
        self.assertIs(FakeHost.receive,original)
        self.assertEqual(ledger['observedAttempts']['task']['outerExec'],1)
        self.assertTrue(saved)


if __name__=='__main__':unittest.main()
