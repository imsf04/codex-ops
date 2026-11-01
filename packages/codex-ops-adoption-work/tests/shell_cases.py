"""Real shell cases for the deterministic host driver."""
import json
from pathlib import Path
import re


def shell_command(case, python):
    fixture = Path(__file__).with_name('shell_fixture.py')
    return f'& "{python}" "{fixture}"' + (' --long' if 'long' in case else '') + (' --fail' if 'fail' in case else '') + (' --silent' if 'silent' in case else '') + '; exit $LASTEXITCODE'


def nested(case, python):
    command = shell_command(case, python)
    expected_exit = 7 if 'fail' in case else 0
    script = '''// @exec: {"max_output_tokens":100000}
const parts=[]; let polls=0;
let r=await tools.exec_command({cmd:COMMAND, max_output_tokens:100000, yield_time_ms:1000});
parts.push(r); const initial=r;
while(r.session_id && r.exit_code===undefined){
  if(++polls>60)throw new Error('POLL_LIMIT');
  r=await tools.write_stdin({session_id:r.session_id,chars:'',yield_time_ms:1000,max_output_tokens:100000}); parts.push(r);
}
const combined=parts.map(p=>p.output).join('');
// Native stdout/stderr pipes may interleave inside a line. Check stdout records
// after removing only the known stderr marker; retain the original result below.
const stdoutRecords=combined.replace(/STDERR_FAILURE_SENTINEL exit=7\\r?\\n/g,'');
for(const part of parts){
  if(typeof part.output!=='string' || typeof part.chunk_id!=='string' || typeof part.wall_time_seconds!=='number')throw new Error('SHELL_ENVELOPE_CHANGED');
  if(part.session_id!==undefined && part.session_id!==initial.session_id)throw new Error('SESSION_ID_CHANGED');
}
text({diagnostic:'SHELL_SHAPE',expectedExit:EXIT,exit:r.exit_code,polls,keys:parts.map(p=>Object.keys(p)),length:combined.length,begin:combined.includes('PHASE_0_BEGIN'),end:combined.includes('PHASE_2_END'),unicode:combined.includes('完整值'),stderr:combined.includes('STDERR_FAILURE_SENTINEL')});
if(r.exit_code!==EXIT || !combined.includes('PHASE_0_BEGIN') || !combined.includes('PHASE_2_END') || !combined.includes('完整值'))throw new Error('SHELL_RAW_VALUE_CHANGED');
for(let phase=0;phase<3;phase++)for(let row=0;row<80;row++)if(!stdoutRecords.includes(phase+':'+row+':完整值:'+('abcdef0123456789'.repeat(8))))throw new Error('MISSING_SHELL_RECORD');
if(EXIT!==0 && !combined.includes('STDERR_FAILURE_SENTINEL'))throw new Error('STDERR_LOST');
if(LONG && (!initial.session_id || polls<2))throw new Error('POLL_PATH_NOT_TESTED');
text({assertion:'SHELL_RAW_ASSERTION_PASSED',exit:r.exit_code,polls,initialSession:initial.session_id,characters:combined.length,keys:parts.map(p=>Object.keys(p))});
text(parts);
'''.replace('EXIT', str(expected_exit)).replace('LONG', str('long' in case).lower()).replace('COMMAND', json.dumps(command))
    return {'type': 'custom_tool_call', 'id': 'tc_shell', 'call_id': 'call_shell', 'name': 'exec', 'input': script}


def direct(case, python, index, body):
    if index == 0:
        return {'type': 'function_call', 'id': 'tc_0', 'call_id': 'call_0', 'name': 'exec_command',
                'arguments': json.dumps({'cmd': shell_command(case, python), 'max_output_tokens': 100000, 'yield_time_ms': 1000})}
    outputs = [x for x in body.get('input', []) if x.get('type') == 'function_call_output']
    if outputs:
        value = outputs[-1]['output']
        rendered = value if isinstance(value, str) else json.dumps(value)
        match = re.search(r'Process running with session ID (\d+)', rendered)
        if match:
            return {'type': 'function_call', 'id': f'tc_{index}', 'call_id': f'call_{index}', 'name': 'write_stdin',
                    'arguments': json.dumps({'session_id': int(match[1]), 'chars': '', 'yield_time_ms': 1000, 'max_output_tokens': 100000})}
    return None
