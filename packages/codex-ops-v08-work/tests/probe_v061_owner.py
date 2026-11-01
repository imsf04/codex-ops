"""Real Code Mode/MCP owner round-trip with an isolated stale ancestor fixture."""
import argparse
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

from run_model_benchmark import Host

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))
import runtime_status


def descendants(pid, ancestor, parents):
    visited = set()
    while pid and pid not in visited:
        if pid == ancestor:
            return True
        visited.add(pid)
        pid = parents.get(pid)
    return False


def server_processes(host, package, proof):
    command = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*python*' } | "
               "Select-Object Name,ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress")
    result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-Command', command],
                            capture_output=True, text=True, encoding='utf-8', check=True, timeout=20)
    candidates = json.loads(result.stdout or '[]')
    if isinstance(candidates, dict):
        candidates = [candidates]
    parents = runtime_status._process_parents()
    owned = [item for item in candidates if descendants(item['ProcessId'], host.process.pid, parents)]
    entry = str(package / 'server.py').replace('\\', '/').lower()
    found = [item for item in owned if entry in (item.get('CommandLine') or '').replace('\\', '/').lower()]
    proof['processDiscovery'] = {'hostPid': host.process.pid, 'ownedPythonProcesses': owned,
                                 'matchingProcesses': [item for item in candidates if entry in (item.get('CommandLine') or '').replace('\\', '/').lower()]}
    assert found, 'No owned candidate MCP process was found in the host lineage: ' + json.dumps({'hostPid': host.process.pid, 'owned': owned})
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=PACKAGE)
    parser.add_argument('--shim', type=Path, default=Path(os.environ['LOCALAPPDATA']) / 'CodexOps/runtime/0.6.1/bin/codex-ops-cli.exe')
    parser.add_argument('--expect-unavailable', action='store_true')
    parser.add_argument('--output', type=Path, default=PACKAGE / 'verification/v061-owner-probe.json')
    args = parser.parse_args()
    package = args.package.resolve()
    directory = Path(tempfile.mkdtemp(prefix='codex-ops-owner-'))
    workspace = directory / 'workspace'
    workspace.mkdir()
    status_root = directory / 'bridge-status'
    status_root.mkdir()
    store = Path(os.environ['LOCALAPPDATA']) / 'CodexOps/verification' / directory.name
    store.mkdir(parents=True)
    proof = {'paidModelCalls': 0, 'package': str(package), 'shim': str(args.shim),
             'workspace': str(workspace), 'bridgeStatusRoot': str(status_root),
             'store': str(store), 'expectUnavailable': args.expect_unavailable,
             'policy': 'existing workspace-write/elevated; no readiness update or permission change'}
    script = ('const value="owner-proof-αβγ-完整|".repeat(2000); text(value); '
              'if(value!=="owner-proof-αβγ-完整|".repeat(2000))throw new Error("SOURCE_VALUE_CHANGED"); '
              'text("OWNER_VALUE_INTACT");')
    traces, phase = [], {'value': 0}

    def inject_stale():
        proof['mcpProcesses'] = server_processes(host, package, proof)
        now = time.time()
        proof['staleFixtures'] = []
        for process in proof['mcpProcesses']:
            pid = process['ProcessId']
            stale = {'version': 1, 'runtimeVersion': 'fixture-stale', 'pid': 999999, 'shimPid': pid,
                     'nativeHostPid': 0, 'startedAt': now - 7200, 'updatedAt': now - 3600,
                     'state': 'ready', 'compressionEnabled': True, 'counters': {}, 'fixtureOnly': True}
            path = status_root / f'{pid}.json'
            assert not path.exists(), 'Refuse to overwrite a genuine status in the isolated directory'
            path.write_text(json.dumps(stale), encoding='utf-8')
            proof['staleFixtures'].append(str(path))

    def retrieve(ref):
        return '''const name=ALL_TOOLS.find(t=>t.name.endsWith("__ops_result")).name;
const expected="owner-proof-αβγ-完整|".repeat(2000);let full="",offset=0,pages=0,denied=false;
for(let n=0;n<20;n++){
 const r=await tools[name]({ref:__REF__,view:"raw",offset,max_bytes:16000});
 const page=r.structuredContent??JSON.parse(r.content[0].text);
 if(page.status==="error"){
   if(page.error?.code!=="REFERENCE_UNAVAILABLE")throw new Error(JSON.stringify(page));
   denied=true;text({ownerProbe:"denied",code:page.error.code});break;
 }
 if(typeof page.text!=="string")throw new Error("INVALID_PAGE");
 full+=page.text;pages++;
 if(page.nextOffset==null)break;offset=page.nextOffset;
}
if(EXPECT_DENIED){if(!denied)throw new Error("EXPECTED_OWNER_REJECTION_MISSING");text("EXPECTED_OWNER_REJECTION");}
else{if(denied)throw new Error("OWNER_LOOKUP_FAILED");if(full!==expected)throw new Error("RAW_MISMATCH");text({ownerRoundtrip:true,characters:full.length,pages});text("OWNER_RAW_EXACT");}'''.replace('__REF__', json.dumps(ref)).replace('EXPECT_DENIED', str(args.expect_unavailable).lower())

    class Model(http.server.BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            outputs = [row for row in body['input'] if row.get('type', '').endswith('_output')]
            rendered = json.dumps(outputs[-1:], ensure_ascii=False)
            number = len(traces) + 1
            running = re.search(r'Script running with cell ID ([A-Za-z0-9_-]+)', rendered)
            if running:
                item = {'type': 'function_call', 'id': f'wait_{number}', 'call_id': f'wait_{number}',
                        'name': 'wait', 'arguments': json.dumps({'cell_id': running[1], 'yield_time_ms': 1000, 'max_tokens': 10000})}
            elif phase['value'] == 0:
                ready = 'const n=ALL_TOOLS.find(t=>t.name.endsWith("__ops_stats")).name; const r=await tools[n]({}); const v=r.structuredContent??JSON.parse(r.content[0].text); if(v.status==="error")throw new Error(JSON.stringify(v));text("MCP_READY");'
                item = {'type': 'custom_tool_call', 'id': 'ready', 'call_id': 'ready', 'name': 'exec', 'input': ready}
                phase['value'] = 1
            elif phase['value'] == 1:
                assert 'MCP_READY' in rendered, 'MCP ready call did not complete'
                inject_stale()
                item = {'type': 'custom_tool_call', 'id': 'emit', 'call_id': 'emit', 'name': 'exec', 'input': script}
                phase['value'] = 2
            elif phase['value'] == 2:
                match = re.search(r'ops://[a-f0-9]{48}', rendered)
                assert match, 'Automatic reference was not emitted'
                proof['reference'] = match[0]
                item = {'type': 'custom_tool_call', 'id': 'retrieve', 'call_id': 'retrieve',
                        'name': 'exec', 'input': retrieve(match[0])}
                phase['value'] = 3
            else:
                item = {'type': 'message', 'id': 'done', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': 'DONE', 'annotations': []}]}
            traces.append({'request': number, 'outputs': outputs, 'responseItem': item})
            response = {'id': f'owner_{number}', 'object': 'response', 'status': 'completed', 'output': [item],
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
    settings = ['model_provider="owner_probe"', 'model_providers.owner_probe.name="Local owner probe"',
                'model_providers.owner_probe.base_url=' + json.dumps(f'http://127.0.0.1:{model.server_port}/v1'),
                'model_providers.owner_probe.wire_api="responses"', 'model_providers.owner_probe.requires_openai_auth=false',
                'mcp_servers.ops_bench.command=' + json.dumps(sys.executable),
                'mcp_servers.ops_bench.args=' + json.dumps([str(package / 'server.py')]),
                'mcp_servers.ops_bench.enabled=true', 'mcp_servers.ops_bench.startup_timeout_sec=30',
                'mcp_servers.ops_bench.env.CODEX_OPS_STORE=' + json.dumps(str(store)),
                'mcp_servers.ops_bench.env.CODEX_OPS_MEASUREMENT_ORIGIN="validation"',
                'mcp_servers.ops_bench.env.CODEX_OPS_BRIDGE_STATUS=' + json.dumps(str(status_root)),
                'mcp_servers.ops_bench.env.CODEX_OPS_AUTO_OUTPUT="0"',
                'mcp_servers.ops_bench.env.CODEX_OPS_BRIDGE_SHIM_PID=""']
    with patch.dict(os.environ, {'CODEX_OPS_BRIDGE_STATUS': str(status_root)}):
        host = Host(args.shim, workspace, store, [part for setting in settings for part in ('-c', setting)])
    try:
        host.request('initialize', {'clientInfo': {'name': 'v061-owner-probe', 'version': '0.1'},
                                    'capabilities': {'experimentalApi': True}})
        host.send({'method': 'initialized'})
        proof['readiness'] = host.request('windowsSandbox/readiness', None)
        assert proof['readiness']['status'] == 'ready'
        status = host.request('mcpServerStatus/list', {'serverName': 'ops_bench', 'detail': 'toolsAndAuthOnly'})
        assert status['data'][0]['toolsError'] is None and len(status['data'][0]['tools']) == 8
        started = host.request('thread/start', {'cwd': str(workspace), 'ephemeral': True, 'model': 'gpt-6.1-terra',
                                               'sandbox': 'workspace-write', 'approvalPolicy': 'never'})
        host.request('turn/start', {'threadId': started['thread']['id'],
                                   'input': [{'type': 'text', 'text': 'Run the deterministic owner probe.'}]})
        deadline = time.monotonic() + 90
        while host.turn is None and time.monotonic() < deadline:
            host.receive(max(0.1, deadline - time.monotonic()))
        proof['turn'] = host.turn
        rendered = json.dumps([entry['outputs'] for entry in traces], ensure_ascii=False)
        marker = 'EXPECTED_OWNER_REJECTION' if args.expect_unavailable else 'OWNER_RAW_EXACT'
        assert host.turn is not None and host.turn['status'] == 'completed'
        assert marker in rendered, 'Native owner round-trip did not produce the required marker'
        assert 'OWNER_VALUE_INTACT' in rendered
        assert not any(error in rendered for error in ('OWNER_LOOKUP_FAILED', 'RAW_MISMATCH', 'EXPECTED_OWNER_REJECTION_MISSING'))
        proof['passed'] = True
    finally:
        host.close()
        model.shutdown()
        proof['localModelResponses'] = len(traces)
        proof['eventsPath'] = str(host.events_path)
        proof['tracePath'] = str(directory / 'model-trace.json')
        (directory / 'model-trace.json').write_text(json.dumps(traces, indent=2, ensure_ascii=False), encoding='utf-8')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(proof, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'passed': proof['passed'], 'expectUnavailable': args.expect_unavailable,
                      'reference': proof.get('reference'), 'output': str(args.output)}), flush=True)


if __name__ == '__main__':
    main()
