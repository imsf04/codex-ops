"""No-model native cwd probe; never changes sandbox readiness or policy."""
import json
import http.server
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import re
import time

from run_model_benchmark import Host

root = Path(__file__).resolve().parents[1]
workspace = Path(tempfile.mkdtemp(prefix='codex-ops-cwd-'))
(workspace / 'probe.txt').write_text('OWNED_CWD_FIXTURE', encoding='utf-8')
store = Path(os.environ['LOCALAPPDATA']) / 'CodexOps/verification' / workspace.name
store.mkdir(parents=True)
shim = Path(os.environ['LOCALAPPDATA']) / 'CodexOps/runtime/0.6.0/bin/codex-ops-cli.exe'
host = Host(shim, workspace, store)
report = {'workspace': str(workspace), 'shim': str(shim), 'paidModelCalls': 0,
          'policy': 'existing workspace-write/elevated Windows sandbox, approval never', 'cases': []}
try:
    host.request('initialize', {'clientInfo': {'name': 'v061-cwd-probe', 'version': '0.1'},
                                'capabilities': {'experimentalApi': True}})
    host.send({'method': 'initialized'})
    report['readiness'] = host.request('windowsSandbox/readiness', None)
    if report['readiness']['status'] != 'ready':
        raise RuntimeError('Readiness is not ready; no update or policy change was attempted')
    started = host.request('thread/start', {'cwd': str(workspace), 'ephemeral': True,
                                           'sandbox': 'workspace-write', 'approvalPolicy': 'never'})
    report['threadCwd'] = started['thread']['cwd']
    pwsh = shutil.which('pwsh')
    assert pwsh
    python = str(Path(sys.base_prefix) / 'python.exe')
    observe = "[ordered]@{provider=(Get-Location).Path;process=[Environment]::CurrentDirectory;relative=(Test-Path -LiteralPath './probe.txt')} | ConvertTo-Json -Compress"
    quote = "'" + str(workspace).replace("'", "''") + "'"
    cases = [
        ('powershell_declared_cwd', [pwsh, '-NoProfile', '-Command', observe]),
        ('python_declared_cwd', [python, '-I', '-c', 'import os,json; print(json.dumps({"cwd":os.getcwd(),"relative":os.path.isfile("probe.txt")}))']),
        ('powershell_set_location', [pwsh, '-NoProfile', '-Command', 'Set-Location -LiteralPath ' + quote + ' -ErrorAction Stop\n' + observe]),
        ('powershell_working_directory_flag', [pwsh, '-NoProfile', '-WorkingDirectory', str(workspace), '-Command', observe]),
        ('python_absolute_path', [python, '-I', '-c', 'import pathlib,json; print(json.dumps({"text":pathlib.Path(' + repr(str(workspace / 'probe.txt')) + ').read_text()}))'])]
    for name, command in cases:
        response = host.request('command/exec', {'command': command, 'cwd': str(workspace), 'timeoutMs': 30000}, timeout=45)
        report['cases'].append({'name': name, 'declaredCwd': str(workspace), **response})
        print(json.dumps({'name': name, **response}, ensure_ascii=False), flush=True)
finally:
    host.close()
    (root / 'verification').mkdir(exist_ok=True)
    (root / 'verification/v061-cwd-probe.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')

# Match the model-facing functions.exec -> exec_command route with deterministic
# localhost responses. No paid model request is made and no native policy changes.
def tagged(name):
    return observe.replace('[ordered]@{', "[ordered]@{probe='" + name + "';")


workdir = str(workspace)
code_cases = [
    {'cmd': tagged('default_cwd'), 'max_output_tokens': 1000},
    {'cmd': tagged('explicit_workdir'), 'workdir': workdir, 'max_output_tokens': 1000},
    {'cmd': tagged('workdir_no_login'), 'workdir': workdir, 'login': False, 'max_output_tokens': 1000},
    {'cmd': 'Set-Location -LiteralPath ' + quote + ' -ErrorAction Stop\n' + tagged('set_location'),
     'workdir': workdir, 'max_output_tokens': 1000},
    {'cmd': "& '" + python.replace("'", "''") + "' -I -c 'import os,json; print(json.dumps({\"probe\":\"python_workdir\",\"cwd\":os.getcwd(),\"relative\":os.path.isfile(\"probe.txt\")}))'",
     'workdir': workdir, 'max_output_tokens': 1000}]
script = '// @exec: {"max_output_tokens":10000}\nfor(const args of ' + json.dumps(code_cases) + '){const r=await tools.exec_command(args);text(r);}'
requests = []


class Model(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        requests.append(body)
        count = len(requests)
        item = {'type': 'custom_tool_call', 'id': 'tc_1', 'call_id': 'call_1', 'name': 'exec', 'input': script}
        if count > 1:
            item = {'type': 'message', 'id': 'msg_done', 'role': 'assistant', 'status': 'completed',
                    'content': [{'type': 'output_text', 'text': 'DONE', 'annotations': []}]}
            output = json.dumps([row for row in body['input'] if row.get('type', '').endswith('_output')][-1:])
            running = re.search(r'Script running with cell ID ([A-Za-z0-9_-]+)', output)
            if running:
                item = {'type': 'function_call', 'id': 'wait_' + str(count), 'call_id': 'wait_' + str(count),
                        'name': 'wait', 'arguments': json.dumps({'cell_id': running[1], 'yield_time_ms': 1000, 'max_tokens': 10000})}
        response = {'id': 'probe_' + str(count), 'object': 'response', 'status': 'completed', 'output': [item],
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


model = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Model)
threading.Thread(target=model.serve_forever, daemon=True).start()
settings = ['model_provider="cwd_probe"', 'model_providers.cwd_probe.name="Local deterministic cwd probe"',
            'model_providers.cwd_probe.base_url=' + json.dumps(f'http://127.0.0.1:{model.server_port}/v1'),
            'model_providers.cwd_probe.wire_api="responses"', 'model_providers.cwd_probe.requires_openai_auth=false']
host = Host(shim, workspace, store, [part for setting in settings for part in ('-c', setting)], artifact_prefix='code-')
try:
    host.request('initialize', {'clientInfo': {'name': 'v061-cwd-code-mode', 'version': '0.1'},
                                'capabilities': {'experimentalApi': True}})
    host.send({'method': 'initialized'})
    report['codeModeReadiness'] = host.request('windowsSandbox/readiness', None)
    assert report['codeModeReadiness']['status'] == 'ready'
    started = host.request('thread/start', {'cwd': str(workspace), 'ephemeral': True, 'model': 'gpt-6.1-terra',
                                           'sandbox': 'workspace-write', 'approvalPolicy': 'never'})
    host.request('turn/start', {'threadId': started['thread']['id'],
                               'input': [{'type': 'text', 'text': 'Run the deterministic local cwd probe.'}]})
    deadline = time.monotonic() + 90
    while host.turn is None and time.monotonic() < deadline:
        host.receive(max(0.1, deadline - time.monotonic()))
    report['codeModeTurn'] = host.turn
    assert host.turn is not None
finally:
    host.close()
    model.shutdown()
    report['codeModeCases'] = []
    for line in host.events_path.read_text(encoding='utf-8').splitlines():
        event = json.loads(line)
        item = event.get('params', {}).get('item', {})
        if event.get('method') == 'item/completed' and item.get('type') == 'commandExecution':
            report['codeModeCases'].append({key: item.get(key) for key in ('command', 'cwd', 'status', 'exitCode', 'aggregatedOutput')})
    report['localModelResponses'] = len(requests)
    (root / 'verification/v061-cwd-probe.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'codeModeCases': report['codeModeCases'], 'turn': report.get('codeModeTurn')}, ensure_ascii=False), flush=True)
