"""Opt-in installed native protocol smoke; localhost responses, zero paid calls."""
import argparse
import datetime
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import threading
from unittest.mock import patch
import uuid
import winreg

import v080_native_host
from probe_app_server import config_entries, home_inputs

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home() / '.codex'
LIVE = ROOT.with_name('codex-ops')
INSTALLED = HOME / 'plugins/cache/personal/codex-ops/0.8.0'
MARKER = 'V080_INSTALLED_PROTOCOL_PROOF:'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding():
    descriptor = INSTALLED / '.mcp.json'
    server = json.loads(descriptor.read_text(encoding='utf-8'))['mcpServers']['codex_ops']
    entry = next(Path(arg) for arg in server['args'] if arg.endswith('server.py'))
    assert entry.samefile(LIVE / 'server.py'), 'Installed MCP must resolve to promoted LIVE source'
    runtime = Path(os.environ['LOCALAPPDATA']) / 'CodexOps/runtime/0.8.0'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
        selected = winreg.QueryValueEx(key, 'CODEX_CLI_PATH')[0]
    assert Path(selected).samefile(runtime / 'bin/codex-ops-cli.exe'), '0.8 must already be selected'
    bundle = json.loads((runtime / 'bundle.json').read_text(encoding='utf-8'))
    assert bundle['version'] == '0.8.0'
    assert {name: sha(runtime / name) for name in bundle['files']} == bundle['files']
    for name, expected in bundle['files'].items():
        source = LIVE / ('bin/codex-ops-cli.exe' if name == 'bin/codex.exe' else name)
        assert sha(source) == expected, 'Staged runtime differs from promoted LIVE: ' + name
    quality = json.loads((LIVE / 'verification/quality/crap.json').read_text(encoding='utf-8'))
    sources = {name: sha(LIVE / name) for name in quality['sourceSha256']}
    assert sources == quality['sourceSha256'], 'LIVE sources must match final quality receipt'
    rust = json.loads((LIVE / 'verification/v080-kernel-build.json').read_text(encoding='utf-8'))
    assert sha(LIVE / rust['binary']) == rust['sha256']
    assert {name: sha(LIVE / name) for name in rust['sourceSha256']} == rust['sourceSha256']
    return server, {'installed': str(INSTALLED), 'live': str(LIVE), 'selectedRuntime': str(runtime),
                    'descriptorSha256': sha(descriptor), 'runtimeFilesSha256': bundle['files'],
                    'python': server['command'],
                    'pythonSha256': sha(Path(server['command'])), 'sourceSha256': sources,
                    'rustBinarySha256': rust['sha256'], 'rustSourceSha256': rust['sourceSha256']}


def script(workspace):
    return 'const root=' + json.dumps(str(workspace)) + ';\n' + r'''
const name=ALL_TOOLS.find(t=>t.name.endsWith("__ops_workflow")||t.name==="ops_workflow")?.name;
if(!name)throw Error("NO_INSTALLED_WORKFLOW");
const unpack=r=>{const v=r.structuredContent??JSON.parse(r.content[0].text);return v.kind==="inline"?v.value:v;};
const args={root,question:"Where is POLICY_ALPHA selected?",args:{paths:["settings.py"]}};
const direct=await tools[name](args), before=JSON.stringify(direct), value=unpack(direct);
if(value.evidenceState!=="collected"||value.workingSet?.state!=="saved")throw Error("DIRECT_ENTRY_FAILED:"+JSON.stringify(value));
const recovered=unpack(await tools[name]({root,operation:"working_set",args:{action:"resume"}}));
if(!recovered.items?.some(item=>item.state==="current"))throw Error("AUTOMATIC_RESUME_FAILED:"+JSON.stringify(recovered));
const reused=unpack(await tools[name](args));
if(!reused.evidenceReuse?.hit||reused.evidenceReuse.revisionsChecked!==1)throw Error("REVISION_REUSE_FAILED:"+JSON.stringify(reused));
if(before!==JSON.stringify(direct))throw Error("ORIGINAL_VALUE_CHANGED");
if(!value.items.some(item=>item.text.includes("POLICY_ALPHA")))throw Error("SOURCE_EVIDENCE_MISSING");
text("V080_INSTALLED_PROTOCOL_PROOF:"+JSON.stringify({direct:true,automaticResume:true,originalIntact:true,
  reuse:reused.evidenceReuse,sources:value.items.map(item=>({source:item.source,location:item.location,text:item.text})),
  kernel:value.coverage?.kernel,workingSet:value.workingSet}));
'''


class Provider(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append(body)
        index = len(self.server.requests)
        (self.server.audit / f'local-provider-{index}.json').write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
        if index == 1:
            item = {'type': 'custom_tool_call', 'id': 'exec_smoke', 'call_id': 'call_smoke',
                    'name': 'exec', 'input': self.server.script}
        else:
            outputs = [row for row in body['input'] if row.get('type', '').endswith('_output')]
            rendered = json.dumps(outputs[-1]) if outputs else ''
            match = re.search(r'Script running with cell ID ([A-Za-z0-9_-]+)', rendered)
            item = {'type': 'message', 'id': 'done', 'role': 'assistant', 'status': 'completed',
                    'content': [{'type': 'output_text', 'text': 'Protocol smoke finished.', 'annotations': []}]}
            if match:
                item = {'type': 'function_call', 'id': f'wait_{index}', 'call_id': f'call_wait_{index}',
                        'name': 'wait', 'arguments': json.dumps({'cell_id': match[1], 'yield_time_ms': 1000, 'max_tokens': 10000})}
        response = {'id': f'local_{index}', 'object': 'response', 'status': 'completed', 'output': [item],
                    'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2}}
        events = [{'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
                  {'type': 'response.output_item.added', 'output_index': 0, 'item': item},
                  {'type': 'response.output_item.done', 'output_index': 0, 'item': item},
                  {'type': 'response.completed', 'response': response}]
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        for event in events:
            self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
        self.wfile.flush()


def text_values(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'text' and isinstance(item, str):
                yield item
            else:
                yield from text_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from text_values(item)


def smoke():
    before = home_inputs(HOME)
    descriptor, bound = binding()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')
    audit = ROOT / 'verification/installed-native-smoke' / stamp
    audit.mkdir(parents=True, exist_ok=False)
    workspace = Path('C:/Temp/CodexOpsAcceptance-v080') / ('installed-' + uuid.uuid4().hex)
    workspace.mkdir(parents=True)
    workspace = workspace.resolve()
    (workspace / 'settings.py').write_text('POLICY_ALPHA = "allow"\n\ndef selected_policy():\n    return POLICY_ALPHA\n', encoding='utf-8')
    model = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    model.requests, model.audit, model.script = [], audit, script(workspace)
    threading.Thread(target=model.serve_forever, daemon=True).start()
    overrides = {'model': 'gpt-5.4', 'model_provider': 'installed_smoke', 'windows': {'sandbox': 'elevated'},
                 'model_providers': {'installed_smoke': {'name': 'Local deterministic protocol smoke',
                 'base_url': f'http://127.0.0.1:{model.server_port}/v1', 'wire_api': 'responses', 'requires_openai_auth': False}}}
    extra = [item for value in config_entries(overrides) for item in ('-c', value)]
    original_flags = v080_native_host.flags
    config = {'home': str(HOME), 'package': str(LIVE), 'toolCount': 8, 'serverName': 'codex_ops',
              'executable': str(Path(bound['selectedRuntime']) / 'bin/codex-ops-cli.exe')}
    report = {'passed': False, 'kind': 'deterministic-native-protocol-smoke', 'paidModelCalls': 0,
              'realModelAdoptionEvidence': False, 'binding': bound, 'workspace': str(workspace),
              'classification': 'Parent process inherits validation origin; installed MCP env is unchanged. Synthetic provider usage is not cost evidence.'}
    host = None
    try:
        with patch.object(v080_native_host, 'flags', lambda effort, cfg: original_flags(effort, cfg) + extra):
            host = v080_native_host.NativeHost(config, workspace, audit / 'store')
        host.open(workspace)
        hooks = [hook for group in host.hooks['data'] for hook in group['hooks']
                 if hook.get('key', '').startswith('codex-ops@personal:')]
        assert len(hooks) == 2 and all(hook['enabled'] and hook['trustStatus'] == 'trusted' for hook in hooks), hooks
        skills = [skill for group in host.skills['data'] for skill in group['skills']
                  if Path(skill['path']).resolve() == (INSTALLED / 'skills/compact-output/SKILL.md').resolve()]
        assert len(skills) == 1 and skills[0]['enabled'], skills
        code = 'import sys,json;sys.path.insert(0,sys.argv[1]);import runtime_status;print(json.dumps({"python":sys.executable,"runtime":runtime_status.current()}))'
        runtime = host.request('command/exec', {'command': [descriptor['command'], '-I', '-c', code, str(LIVE)],
                               'cwd': str(workspace), 'timeoutMs': 30000}, timeout=45)
        assert runtime['exitCode'] == 0, runtime
        status = json.loads(runtime['stdout'])
        assert Path(status['python']).samefile(descriptor['command'])
        assert status['runtime']['runtimeVersion'] == '0.8.0' and status['runtime']['activeForThisProcess'], status
        host.run_phase('Run the installed plugin protocol smoke.', 120)
        outputs = [row for body in model.requests for row in body.get('input', []) if row.get('type', '').endswith('_output')]
        proofs = [json.loads(line[len(MARKER):]) for value in text_values(outputs)
                  for line in value.splitlines() if line.startswith(MARKER)]
        assert proofs and host.turn['status'] == 'completed', host.result()
        report.update(passed=True, proofs=proofs, native=host.result(), hooks=hooks, skills=skills, runtime=status,
                      providerRequests=len(model.requests), nativeAudit=str(host.rpc_path))
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        if host:
            host.close()
        model.shutdown()
        model.server_close()
        report['configAuthUnchanged'] = before == home_inputs(HOME)
        report['configAuthSha256'] = home_inputs(HOME)
        report['passed'] = report['passed'] and report['configAuthUnchanged']
        (audit / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    assert report['passed'], report
    (ROOT / 'verification/v080-installed-native-smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'passed': True, 'report': str(audit / 'report.json'), 'paidModelCalls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Only after original sandbox restore and 0.8 promotion')
    args = parser.parse_args()
    print(json.dumps(smoke() if args.execute else {'preparedOnly': True, 'requires': 'Official global sandbox restored, 0.8 installed and selected'}))
