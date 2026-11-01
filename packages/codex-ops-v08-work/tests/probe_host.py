"""Deterministic local Responses server: exercise the installed host, no model calls."""
import argparse
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import tomllib
import shell_cases
import re
from native_cli import native_cli, mcp_python


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', default='discover')
    parser.add_argument('--mode', default='none')
    parser.add_argument('--installed', action='store_true')
    parser.add_argument('--workspace', help='Reuse an initialized test workspace and its sandbox; keep receipts separate')
    parser.add_argument('--persist-test', action='store_true', help='Keep transcript only inside the isolated test home')
    parser.add_argument('--installed-test-home', action='store_true', help='Use the native plugin package installed in the isolated home')
    args = parser.parse_args()
    workspace = Path(args.workspace) if args.workspace else Path(tempfile.mkdtemp(prefix='codex-ops-probe-'))
    root = Path(tempfile.mkdtemp(prefix='run-', dir=workspace)) if args.workspace else workspace
    home = workspace / 'home'
    home.mkdir(exist_ok=True)
    requests = []
    steps = []
    python = mcp_python()
    shell_case = args.case.startswith('shell_')
    direct_case = args.case == 'direct' or (shell_case and '_direct' in args.case)
    if args.case.startswith('outer_'):
        source = 'const data={records:Array.from({length:200},(_,id)=>({id,body:"完整".repeat(80)})),bool:false,nil:null};'
        source += {'outer_text': 'text(data);', 'outer_notify': 'notify(data);',
                   'outer_yield': 'text(data);await yield_control();await new Promise(r=>setTimeout(r,100));notify(data);'}[args.case]
        source += 'if(data.records.length!==200||data.records[199].id!==199)throw new Error("RAW_VALUE_CHANGED");text("OUTER_RAW_INTACT");'
        steps.append({'type': 'custom_tool_call', 'id': 'tc_outer', 'call_id': 'call_outer', 'name': 'exec',
                      'input': '// @exec: {"max_output_tokens":100000}\n' + source})
    if shell_case and not direct_case:
        steps.append(shell_cases.nested(args.case, python))
    if args.case in ('nested', 'capture'):
        script = '''// @exec: {"max_output_tokens": 100000}
const t = ALL_TOOLS.find(t=>t.name.endsWith('fixture')); if (!t) throw new Error(JSON.stringify(ALL_TOOLS.map(t=>t.name))); const r = await tools[t.name]({});
const d = r.structuredContent ?? JSON.parse(r.content[0].text);
if (d.marker !== 'RAW_VALUE_SENTINEL' || d.records.length !== 400 || d.records[399].id !== 399 || d.nested.unicode !== '完整值' || d.nested.bool !== false || d.nested.null !== null) throw new Error('RAW_VALUE_CHANGED');
text('RAW_ASSERTION_PASSED'); text(r);'''
        if args.case == 'capture':
            script = script.replace('text(r);', '''const capture = ALL_TOOLS.find(t=>t.name.endsWith('ops_capture'));
const shown = await tools[capture.name]({value:r});
const receipt = shown.structuredContent ?? JSON.parse(shown.content[0].text);
if (!receipt.ref) throw new Error('CAPTURE_FAILED');
store('probe_ref',receipt.ref); store('probe_raw',JSON.stringify(r)); text(shown);''')
        steps.append({'type': 'custom_tool_call', 'id': 'tc_1', 'call_id': 'call_1', 'name': 'exec', 'input': script})
        if args.case == 'capture':
            followup = '''const name=ALL_TOOLS.find(t=>t.name.endsWith('ops_result')).name;
const unwrap=r=>r.structuredContent ?? JSON.parse(r.content[0].text);
const projected=unwrap(await tools[name]({ref:load('probe_ref'),path:'/records',fields:['id'],query:'399'}));
if(projected.items.length!==1 || projected.items[0].value.id!==399) throw new Error('PROJECTION_FAILED');
let raw='',offset=0,pages=0;
while(true){const page=unwrap(await tools[name]({ref:load('probe_ref'),view:'raw',offset,max_bytes:16000}));
if(page.status==='error') throw new Error(JSON.stringify(page)); raw+=page.text; pages++; if(page.complete)break; offset=page.nextOffset;}
if(JSON.stringify(JSON.parse(raw))!==load('probe_raw')) throw new Error('ROUNDTRIP_FAILED');
text({assertion:'FULL_ROUNDTRIP_PASSED',pages,projected:projected.items});'''
            steps.append({'type': 'custom_tool_call', 'id': 'tc_2', 'call_id': 'call_2', 'name': 'exec', 'input': followup})
    elif args.case == 'shell':
        script = '''const r = await tools.exec_command({cmd:"Write-Output ('RAW_SHELL_SENTINEL' + ('x' * 15000))",max_output_tokens:12000});
text({rawIntact:r.output.includes('RAW_SHELL_SENTINEL') && r.output.length > 15000,exit:r.exit_code}); text(r);'''
        steps.append({'type': 'custom_tool_call', 'id': 'tc_1', 'call_id': 'call_1', 'name': 'exec', 'input': script})
    elif args.case == 'direct':
        steps.append({'type': 'function_call', 'id': 'tc_1', 'call_id': 'call_1', 'namespace': 'mcp__probe', 'name': 'fixture', 'arguments': '{}'})

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            body = json.loads(raw)
            requests.append(body)
            (root / f'request-{len(requests)}.json').write_text(json.dumps(body, indent=2), encoding='utf-8')
            index = len(requests) - 1
            output = steps[index] if index < len(steps) else {
                'type': 'message', 'id': 'msg_done', 'role': 'assistant', 'status': 'completed',
                'content': [{'type': 'output_text', 'text': 'PROBE_DONE', 'annotations': []}],
            }
            if shell_case and direct_case:
                output = shell_cases.direct(args.case, python, index, body) or output
            if args.case == 'outer_yield' and index > 0:
                results = [v for v in body.get('input', []) if v.get('type', '').endswith('_output')]
                rendered = json.dumps(results[-1]) if results else ''
                match = re.search(r'Script running with cell ID ([A-Za-z0-9_-]+)', rendered)
                if match:
                    output = {'type': 'function_call', 'id': f'wait_{index}', 'call_id': f'call_wait_{index}',
                              'name': 'wait', 'arguments': json.dumps({'cell_id': match[1], 'yield_time_ms': 1000, 'max_tokens': 100000})}
            response = {'id': f'resp_{index}', 'object': 'response', 'status': 'completed',
                        'output': [output], 'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2}}
            events = [
                {'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
                {'type': 'response.output_item.added', 'output_index': 0, 'item': output},
                {'type': 'response.output_item.done', 'output_index': 0, 'item': output},
                {'type': 'response.completed', 'response': response},
            ]
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for event in events:
                self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
            self.wfile.flush()

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    python = mcp_python()
    fixture = Path(__file__).with_name('probe_mcp.py')
    config = f'''model = "gpt-5.4"
model_provider = "probe"
approval_policy = "never"
sandbox_mode = "read-only"
web_search = "disabled"
tool_output_token_limit = 100000
[model_providers.probe]
name = "Local deterministic hook probe"
base_url = "http://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
[features]
apps = false
plugins = false
shell_snapshot = false
multi_agent = false
code_mode = {str(not direct_case).lower()}
code_mode_only = {str(not direct_case).lower()}
[mcp_servers.probe]
command = '{python}'
args = ['-u', '{fixture}']
startup_timeout_sec = 30
required = true
'''
    if shell_case:
        # Match the user's configured Windows execution policy; never change it.
        host_config = tomllib.loads((Path.home() / '.codex/config.toml').read_text(encoding='utf-8'))
        policy = host_config.get('sandbox_mode', 'read-only')
        config = config.replace('sandbox_mode = "read-only"', 'sandbox_mode = ' + json.dumps(policy))
        if host_config.get('windows', {}).get('sandbox'):
            config += '[windows]\nsandbox = ' + json.dumps(host_config['windows']['sandbox']) + '\n'
    if args.installed_test_home:
        assert not args.installed and args.persist_test and args.workspace
        config = config.replace('plugins = false', 'plugins = true')
        config += '\n[plugins."codex-ops@personal"]\nenabled = true\n'
        # Reuse only the exact plugin hashes the user has already authorized.
        host_config = tomllib.loads((Path.home() / '.codex/config.toml').read_text(encoding='utf-8'))
        for key, value in host_config.get('hooks', {}).get('state', {}).items():
            if key.startswith('codex-ops@personal:'):
                config += '\n[hooks.state.' + json.dumps(key) + ']\ntrusted_hash = ' + json.dumps(value['trusted_hash']) + '\n'
    if args.mode in ('production', 'observe') or args.case == 'capture':
        production_python = mcp_python()
        config += f'''[mcp_servers.codex_ops]
command = '{production_python}'
args = ['-u', '{Path(__file__).resolve().parents[1] / "server.py"}']
startup_timeout_sec = 30
required = true
[mcp_servers.codex_ops.env]
CODEX_OPS_STORE = '{root / "store"}'
'''
    (home / 'config.toml').write_text(config, encoding='utf-8')
    if (args.mode == 'none' or args.installed_test_home) and not args.installed:
        (home / 'hooks.json').write_text('{"hooks":{}}', encoding='utf-8')
    if args.mode != 'none' and not args.installed and not args.installed_test_home:
        hook = Path(__file__).with_name('probe_hook.py')
        command_hook = f'& "{python}" "{hook}" "{root}" "{args.mode}"'
        if args.mode == 'production':
            command_hook = f'$env:CODEX_OPS_STORE="{root / "store"}"; & "{production_python}" "{Path(__file__).resolve().parents[1] / "hook.py"}"'
        hook_config = {'hooks': {'PostToolUse': [{'matcher': '.*', 'hooks': [
            {'type': 'command', 'command': command_hook, 'commandWindows': command_hook, 'timeout': 10}
        ]}]}}
        if args.mode == 'audit':
            hook_config['hooks']['PreToolUse'] = hook_config['hooks']['PostToolUse']
        (home / 'hooks.json').write_text(json.dumps(hook_config), encoding='utf-8')
    env = {**os.environ, 'CODEX_HOME': str(home), 'PROBE_ROOT': str(root), 'PROBE_MODE': args.mode}
    command = [native_cli(), 'exec', '--ephemeral', '--skip-git-repo-check', '--json',
               '-C', str(workspace), 'Execute the deterministic local tool protocol test.']
    if args.persist_test:
        assert not args.installed, 'Persistent probes must stay outside the user home'
        command.remove('--ephemeral')
    if args.mode != 'none' and not args.installed and not args.installed_test_home:
        # Isolated home, reviewed fixture only; never modifies persisted user trust.
        command.insert(2, '--dangerously-bypass-hook-trust')
    if args.installed:
        # Use the installed plugin and the user's reviewed trust through the host.
        # Provider and fixture are process-only overrides; no model request leaves localhost.
        env = {**os.environ}
        override = tomllib.loads(config)
        override['features']['plugins'] = True
        override['mcp_servers'].pop('codex_ops', None)
        def flatten(value, prefix=''):
            for key, item in value.items():
                path = prefix + '.' + key if prefix else key
                if isinstance(item, dict):
                    yield from flatten(item, path)
                else:
                    yield path + '=' + json.dumps(item, ensure_ascii=False)
        overrides = [part for setting in flatten(override) for part in ('-c', setting)]
        command[2:2] = overrides
    try:
        result = subprocess.run(command, env=env, capture_output=True, timeout=80, creationflags=subprocess.CREATE_NO_WINDOW)
        (root / 'stdout.jsonl').write_bytes(result.stdout)
        (root / 'stderr.txt').write_bytes(result.stderr)
        replayed = [x for r in requests[1:] for x in r.get('input', []) if x.get('type', '').endswith('_output')]
        outputs = list({x.get('id', x['call_id']): x for x in replayed}.values())
        (root / 'outputs.json').write_text(json.dumps(outputs, indent=2), encoding='utf-8')
        rendered = json.dumps(outputs)
        events = [json.loads(line) for line in (root / 'hooks.jsonl').read_text(encoding='utf-8').splitlines()] if (root / 'hooks.jsonl').exists() else []
        report = {'root': str(root), 'returncode': result.returncode, 'requests': len(requests),
                  'outputBytes': len(rendered), 'rawAssertionPassed': 'RAW_ASSERTION_PASSED' in rendered,
                  'rawValueChanged': 'RAW_VALUE_CHANGED' in rendered, 'feedbackVisible': 'HOOK_COMPACT' in rendered,
                  'rawSentinelVisible': 'RAW_VALUE_SENTINEL' in rendered,
                  'fullRoundtripPassed': 'FULL_ROUNDTRIP_PASSED' in rendered,
                  'scriptError': 'Script error' in rendered,
                  'shellRawPassed': 'SHELL_RAW_ASSERTION_PASSED' in rendered,
                  'outerRawPassed': 'OUTER_RAW_INTACT' in rendered,
                  'sourceCodeBytes': sum(len(s.get('input', s.get('arguments', '')).encode()) for s in steps),
                  'replayedOutputBytes': len(json.dumps(replayed).encode()),
                  'hookTools': [e['tool_name'] for e in events]}
        (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))
        if not requests or result.returncode:
            print(result.stderr.decode(errors='replace')[-3000:])
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
