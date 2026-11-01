import json
from pathlib import Path
import subprocess
import unittest
import sdk_workflow
import verification_workflow


class VerifyTests(unittest.TestCase):
    def test_combines_chunks_without_mutating_values(self):
        values=[{'output':'ERROR first\n','session_id':3},{'output':'tail\n','exit_code':1}]
        before=json.dumps(values);calls=[]
        def invoke(root, operation, args):calls.append((root,operation,args));return {'diagnostics':['first']}
        result=verification_workflow.run('root',{'results':values},invoke)
        self.assertEqual(json.dumps(values),before)
        self.assertIs(result['observations'],values)
        self.assertEqual(result['exitCode'],1)
        self.assertEqual(calls[0][2]['log'],'ERROR first\ntail\n')
        self.assertFalse(result['coverage']['sourceComplete'])

    def test_running_success_unknown_and_oversize(self):
        def forbidden(*args):raise AssertionError('must not diagnose')
        for final,state in [({'session_id':7},'running'),({'exit_code':0},'completed'),({},'unknown')]:
            result=verification_workflow.run('root',{'results':[final]},forbidden)
            self.assertEqual(result['executionState'],state)
        huge={'output':'x'*262145,'exit_code':2}
        self.assertIsNotNone(verification_workflow.run('root',{'results':[huge]},forbidden)['diagnosticSkipped'])
        for args in ({'results':[]},{'results':[None]},{'results':[{'output':3}]},{'results':[{}],'command':'unsafe'}):
            with self.assertRaises(ValueError):verification_workflow.run('root',args,forbidden)

    def test_sdk_native_polling_and_terminal_result(self):
        script=sdk_workflow.SOURCE+'''
const assert = require('node:assert/strict');
(async()=>{
  let executions=0, polls=0, workflow=0;
  const start={session_id:7,output:'ERROR first\\n'};
  const end={exit_code:2,output:'tail\\n'};
  const tools={exec_command:async args=>{executions++;assert.equal(args.workdir,'C:/root');return start;},
    write_stdin:async args=>{polls++;assert.equal(args.session_id,7);assert.equal(args.chars,'');return end;},
    ops_workflow:async args=>{workflow++;assert.equal(args.operation,'verify');assert.deepEqual(args.args.results,[start,end]);return {structuredContent:{status:'completed'}};}};
  const ops=createOps(tools,[{name:'ops_workflow'}],'C:/root');
  const result=await ops.verifyRun({cmd:'explicit-command'});
  assert.equal(result.state,'completed');assert.equal(result.shell,end);assert.equal(result.observations[0],start);
  assert.equal(executions,1);assert.equal(polls,1);assert.equal(workflow,1);
  await assert.rejects(()=>ops.verifyRun({cmd:'x'},{maxPolls:9}));
  await assert.rejects(()=>ops.verifyRun({cmd:'x'},{diagnosticArgs:{logPath:'override'}}));
  await assert.rejects(()=>ops.verifyRun({cmd:'x'},{unknown:true}));
  tools.write_stdin=async()=>start;
  tools.ops_workflow=async()=>({structuredContent:{status:'completed'}});
  const running=await ops.verifyRun({cmd:'long'},{maxPolls:2});assert.equal(running.state,'running');assert.equal(running.observations.length,3);
  tools.exec_command=async()=>{throw Error('native denial');};
  await assert.rejects(()=>ops.verifyRun({cmd:'denied'}),/native denial/);
  process.stdout.write('SDK_VERIFY_OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout,'SDK_VERIFY_OK')


if __name__=='__main__':unittest.main()
