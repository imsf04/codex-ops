"""Actual app-server + native remote Code Mode host + deterministic localhost model."""
import concurrent.futures
import http.server
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import argparse
import re
import sys
import base64
import struct
import zlib

import grpc
from native_cli import native_cli, mcp_python
from coverage_entry import instrument


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=['text', 'error', 'yield', 'mcp', 'media', 'tool_error', 'shell', 'runtime_status', 'progress', 'retrieval'], default='text')
    parser.add_argument('--compress', action='store_true')
    parser.add_argument('--shim', action='store_true')
    parser.add_argument('--shim-path', type=Path)
    parser.add_argument('--production-status', action='store_true')
    parser.add_argument('--coverage', action='store_true', help='Use instrumented test-only Python entrypoints')
    parser.add_argument('--sandbox-workspace', type=Path)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix='codex-ops-appserver-'))
    home = (args.sandbox_workspace or root) / 'home'
    home.mkdir(exist_ok=True)
    os.environ['CODEX_OPS_STORE'] = str(root / 'store')
    os.environ['CODEX_OPS_MEASUREMENT_ORIGIN'] = 'validation'
    status_root = Path(os.environ['LOCALAPPDATA']) / 'CodexOps/bridge' if args.production_status else root / 'bridge-status'
    os.environ['CODEX_OPS_BRIDGE_STATUS'] = str(status_root)
    model_requests, frames = [], []
    prefix = '// @exec: {"max_output_tokens":100000}\n'
    script = prefix + 'const r={records:Array.from({length:200},(_,id)=>({id,body:"完整".repeat(80)}))};text(r);notify(r);if(r.records.length!==200)throw new Error("RAW_CHANGED");text("RAW_INTACT");'
    if args.case == 'error':
        script = prefix + 'text("x".repeat(20000));throw new Error("EXPECTED_FAILURE");'
    elif args.case == 'yield':
        script = prefix + 'const r={records:Array.from({length:200},(_,id)=>({id,body:"完整".repeat(80)}))};text(r);await yield_control();await new Promise(f=>setTimeout(f,100));notify(r);text(r);if(r.records[199].id!==199)throw new Error("RAW_CHANGED");text("RAW_INTACT");'
    elif args.case == 'mcp':
        script = prefix + 'const t=ALL_TOOLS.find(t=>t.name.endsWith("fixture"));const r=await tools[t.name]({});const d=r.structuredContent??JSON.parse(r.content[0].text);text(r);notify(r);if(d.records.length!==400||d.records[399].id!==399||d.nested.unicode!=="完整值"||d.nested.bool!==false||d.nested.null!==null)throw new Error("RAW_CHANGED");text("RAW_INTACT");'
    elif args.case == 'media':
        def png_chunk(name, data):
            return struct.pack('!I', len(data)) + name + data + struct.pack('!I', zlib.crc32(name + data))
        png = b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('!IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
        png += png_chunk(b'IDAT', zlib.compress(b'\x00\x33\x66\x99\xff')) + png_chunk(b'IEND', b'')
        uri = 'data:image/png;base64,' + base64.b64encode(png).decode()
        script = prefix + 'image(' + json.dumps(uri) + ');text("RAW_INTACT");'
    elif args.case == 'tool_error':
        script = prefix + 'let rejected=false;try{await tools.read_mcp_resource({server:"missing_probe",uri:"fixture://missing"});}catch(e){if(!String(e).includes("missing_probe"))throw e;rejected=true;text("TOOL_ERROR_PRESERVED:"+String(e));}if(!rejected)throw new Error("EXPECTED_REJECTION_MISSING");text("RAW_INTACT");'
    elif args.case == 'shell':
        command = "Get-Content -LiteralPath 'C:\\Users\\imsfp\\code\\dsh-ops\\packages\\codex-ops\\tests\\test_core.py' -Raw"
        script = prefix + 'const r=await tools.exec_command({cmd:' + json.dumps(command) + ',max_output_tokens:20000});text(r);if(r.exit_code!==0||!r.output.includes("test_full_roundtrip_and_metadata"))throw new Error("RAW_CHANGED");text("RAW_INTACT");'
    elif args.case == 'runtime_status':
        script = prefix + 'const t=ALL_TOOLS.find(t=>t.name.endsWith("ops_stats"));const r=await tools[t.name]({origin:"validation"});const d=r.structuredContent??JSON.parse(r.content[0].text);text(d.runtimeBridge);if(!d.runtimeBridge.activeForThisProcess||!d.presentationTotals.available||d.presentationTotals.origin!=="validation")throw new Error("BRIDGE_NOT_ATTACHED");text("RAW_INTACT");'
    elif args.case == 'progress':
        script = prefix + 'const p={session_id:42,exit_code:null,output:"running ".repeat(90)};text(p);text({...p,chunk_id:"next"});text({...p,exit_code:7,status:"failed"});if(p.exit_code!==null||p.output.length!==720)throw new Error("RAW_CHANGED");text("RAW_INTACT");'
    elif args.case == 'retrieval':
        script = prefix + 'text("retrieval payload ".repeat(1200));text("RAW_INTACT");'

    class Model(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            model_requests.append(body)
            (root / f'model-request-{len(model_requests)}.json').write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding='utf-8')
            item = {'type': 'custom_tool_call', 'id': 'tc_1', 'call_id': 'call_1', 'name': 'exec', 'input': script} if len(model_requests) == 1 else {
                'type': 'message', 'id': 'msg_done', 'role': 'assistant', 'status': 'completed',
                'content': [{'type': 'output_text', 'text': 'DONE', 'annotations': []}]}
            if len(model_requests) > 1:
                outputs = [x for x in body['input'] if x.get('type', '').endswith('_output')]
                rendered = json.dumps(outputs[-1]) if outputs else ''
                match = re.search(r'Script running with cell ID ([A-Za-z0-9_-]+)', rendered)
                if match:
                    item = {'type': 'function_call', 'id': f'wait_{len(model_requests)}', 'call_id': f'call_wait_{len(model_requests)}',
                            'name': 'wait', 'arguments': json.dumps({'cell_id': match[1], 'yield_time_ms': 1000, 'max_tokens': 100000})}
                if args.case == 'retrieval' and len(model_requests) == 2:
                    ref = re.search(r'ops://[a-f0-9]{48}', rendered)[0]
                    retrieve = 'const t=ALL_TOOLS.find(t=>t.name.endsWith("ops_result"));const r=await tools[t.name]({ref:' + json.dumps(ref) + ',view:"raw",max_bytes:12000});const d=r.structuredContent??JSON.parse(r.content[0].text);text(r);if(!d.text.startsWith("retrieval payload ")||d.offset!==0)throw new Error("RAW_CHANGED");text("RETRIEVAL_PAGE_INTACT");text("RAW_INTACT");'
                    item = {'type': 'custom_tool_call', 'id': 'tc_retrieve', 'call_id': 'call_retrieve', 'name': 'exec', 'input': prefix + retrieve}
            response = {'id': f'resp_{len(model_requests)}', 'object': 'response', 'status': 'completed',
                        'output': [item], 'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2}}
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
    native_port = free_port()
    native_exe = Path(native_cli()).with_name('codex-code-mode-host.exe')
    native = subprocess.Popen([str(native_exe), '--listen', f'grpc://127.0.0.1:{native_port}'],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    upstream = grpc.insecure_channel(f'127.0.0.1:{native_port}', options=[('grpc.max_receive_message_length', 67108864), ('grpc.max_send_message_length', 67108864)])
    grpc.channel_ready_future(upstream).result(timeout=8)

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime_bridge'))
    from grpc_relay import serve
    def record(direction, method, original, presented):
        frames.append({'direction': direction, 'method': method, 'hex': original.hex(), 'presentedHex': presented.hex()})
    upstream.close()
    proxy, upstream, relay, port = serve(f'127.0.0.1:{native_port}', on_frame=record, enabled=args.compress)
    config = f'''model = "gpt-5.4"
model_provider = "probe"
approval_policy = "never"
sandbox_mode = "read-only"
web_search = "disabled"
tool_output_token_limit = 100000
[model_providers.probe]
name = "Local deterministic probe"
base_url = "http://127.0.0.1:{model.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
[features]
code_mode = true
code_mode_only = true
apps = false
plugins = false
multi_agent = false
shell_snapshot = false
'''
    if args.sandbox_workspace:
        import tomllib
        current = tomllib.loads((Path.home() / '.codex/config.toml').read_text(encoding='utf-8'))
        config = config.replace('sandbox_mode = "read-only"', 'sandbox_mode = ' + json.dumps(current['sandbox_mode']))
        config += '\n[windows]\nsandbox = ' + json.dumps(current['windows']['sandbox']) + '\n'
    (home / 'config.toml').write_text(config, encoding='utf-8')
    if args.case == 'mcp':
        python = mcp_python()
        fixture = Path(__file__).with_name('probe_mcp.py').resolve()
        config += f"\n[mcp_servers.probe]\ncommand = '{python}'\nargs = ['-u','{fixture}']\nrequired = true\n"
        (home / 'config.toml').write_text(config, encoding='utf-8')
    if args.case in ('runtime_status', 'retrieval'):
        python = mcp_python()
        entry = Path(__file__).resolve().parents[1] / 'server.py'
        if args.coverage:
            python, entry = Path(sys.executable), instrument(root, entry)
        config += f"\n[mcp_servers.codex_ops]\ncommand = '{python}'\nargs = ['-u','{entry}']\nrequired = true\n"
        config += f"[mcp_servers.codex_ops.env]\nCODEX_OPS_BRIDGE_STATUS = '{status_root}'\n"
        config += f"CODEX_OPS_STORE = '{root / 'store'}'\n"
        (home / 'config.toml').write_text(config, encoding='utf-8')
    command = [native_cli(), 'app-server', '--stdio', '--code-mode-host', f'http://127.0.0.1:{port}']
    environment = {**os.environ, 'CODEX_HOME': str(home)}
    # Do not route isolated probes through the parent Desktop's tool executor.
    for key in ('CODEX_APP_TOOLS_PIPE_PATH', 'BROWSER_USE_PIPE_PATH', 'BROWSER_USE_ACCESS_PIPE_PATH', 'BROWSER_USE_ACCESS_EXECUTOR_ID'):
        environment.pop(key, None)
    if args.shim:
        command = [str(args.shim_path or Path(__file__).resolve().parents[1] / 'bin/codex-ops-cli.exe'), '-c', 'features.code_mode_host=true', 'app-server', '--stdio']
        if args.coverage:
            # Isolated copy: never add instrumentation to the installed runtime.
            binary = root / 'instrumented-bin'
            binary.mkdir()
            shutil.copy2(command[0], binary / 'codex-ops-cli.exe')
            package = Path(__file__).resolve().parents[1]
            settings = {'real-cli.txt': native_cli(), 'bridge-python.txt': sys.executable,
                        'bridge-script.txt': str(instrument(root, package / 'runtime_bridge/manager.py'))}
            for name, value in settings.items():
                (binary / name).write_text(value, encoding='utf-8')
            command[0] = str(binary / 'codex-ops-cli.exe')
        environment.pop('CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY', None)  # Actual Desktop override behavior.
    process = subprocess.Popen(command,
                               env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=(root / 'appserver-stderr.txt').open('wb'), text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
    inbox = queue.Queue()
    def read():
        for line in process.stdout:
            inbox.put(json.loads(line))
    threading.Thread(target=read, daemon=True).start()
    events = []
    def send(value):
        process.stdin.write(json.dumps(value) + '\n')
        process.stdin.flush()
    def request(id, method, params):
        send({'id': id, 'method': method, 'params': params})
        while True:
            message = inbox.get(timeout=40)
            events.append(message)
            if message.get('id') == id:
                assert 'error' not in message, message
                return message['result']
    try:
        request(1, 'initialize', {'clientInfo': {'name': 'code-mode-bridge-probe', 'version': '0.1'}, 'capabilities': {'experimentalApi': True}})
        send({'method': 'initialized'})
        thread = request(2, 'thread/start', {'cwd': str(args.sandbox_workspace or root), 'ephemeral': True})
        request(3, 'turn/start', {'threadId': thread['thread']['id'], 'input': [{'type': 'text', 'text': 'Run the deterministic local protocol fixture.'}]})
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            message = inbox.get(timeout=45)
            events.append(message)
            if message.get('method') == 'turn/completed':
                break
        if args.shim:
            if args.coverage:
                time.sleep(0.3)  # Flush a coverage snapshot before Windows Job teardown.
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                statuses = list(status_root.glob(f'{process.pid}.json'))
                if statuses:
                    bridge_status = json.loads(statuses[0].read_text())
                    if bridge_status['counters']['outboundFrames'] >= 4:
                        break
                time.sleep(0.1)
            assert bridge_status['compressionEnabled'], bridge_status
            (root / 'shim-bridge-status.json').write_text(json.dumps(bridge_status, indent=2), encoding='utf-8')
    finally:
        process.terminate()
        process.wait(timeout=5)
        proxy.stop(0)
        upstream.close()
        relay.close()
        native.terminate()
        native.wait(timeout=5)
        model.shutdown()
        (root / 'grpc-frames.json').write_text(json.dumps(frames, indent=2), encoding='utf-8')
        (root / 'events.json').write_text(json.dumps(events, indent=2), encoding='utf-8')
    last = model_requests[-1] if model_requests else {}
    outputs = [x for x in last.get('input', []) if x.get('type', '').endswith('_output')]
    rendered = json.dumps(outputs, ensure_ascii=False)
    report = {'root': str(root), 'case': args.case, 'compress': args.compress, 'modelRequests': len(model_requests),
              'grpcMethods': sorted(set(x['method'] for x in frames)), 'frames': len(frames),
              'modelVisibleBytes': len(rendered.encode()), 'rawIntact': 'RAW_INTACT' in rendered,
              'expectedError': 'EXPECTED_FAILURE' in rendered, 'rawChanged': 'RAW_CHANGED' in rendered,
              'toolErrorPreserved': 'TOOL_ERROR_PRESERVED:unknown MCP server' in rendered,
              'imagePresent': any(block.get('type') == 'input_image' for item in outputs for block in (item.get('output', []) if isinstance(item.get('output'), list) else [])),
              'references': len(set(re.findall(r'ops://[a-f0-9]{48}', rendered))),
              'inboundUnchanged': all(x['hex'] == x['presentedHex'] for x in frames if x['direction'] == 'to_host'),
              'relay': relay.counts}
    from telemetry import snapshot
    report['presentationTotals'] = snapshot('validation', root / 'store')
    report['progressCompacted'] = 'unchangedPolls' in rendered
    report['retrievalPageIntact'] = 'RETRIEVAL_PAGE_INTACT' in rendered
    if args.shim:
        report['shim'] = True
        report['productionStatusDirectory'] = args.production_status
        report['inboundUnchanged'] = None  # This run uses manager counters, not a packet trace.
        report['relay'] = bridge_status['counters']
        report['nativeHostPid'] = bridge_status['nativeHostPid']
        report['managerPid'] = bridge_status['pid']
    (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
