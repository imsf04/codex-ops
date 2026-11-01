"""Run the user-authorized native setup for the existing isolated test profile."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
from native_cli import native_cli

workspace = Path(os.environ['TEMP']) / 'codex-ops-probe-jrmkhnjv'
assert (workspace / 'home').is_dir()
env = dict(os.environ, CODEX_HOME=str(workspace / 'home'))
process = subprocess.Popen([native_cli(), 'app-server', '--stdio'], env=env,
    cwd=workspace, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
    creationflags=subprocess.CREATE_NO_WINDOW)
inbox = queue.Queue()
def read():
    for line in process.stdout:
        inbox.put(json.loads(line))
threading.Thread(target=read, daemon=True).start()
def send(value):
    process.stdin.write(json.dumps(value) + '\n')
    process.stdin.flush()
def request(number, method, params):
    send({'id': number, 'method': method, 'params': params})
    while True:
        value = inbox.get(timeout=180)
        if value.get('id') == number:
            return value
try:
    request(1, 'initialize', {'clientInfo': {'name': 'codex-ops-verification',
        'version': '0.5.0'}, 'capabilities': {'experimentalApi': True}})
    send({'method': 'initialized'})
    before = request(2, 'windowsSandbox/readiness', None)
    print(json.dumps({'before': before}), flush=True)
    started = request(3, 'windowsSandbox/setupStart', {'mode': 'elevated', 'cwd': str(workspace)})
    print(json.dumps({'started': started}), flush=True)
    if 'error' in started:
        raise RuntimeError(started)
    while True:
        notification = inbox.get(timeout=180)
        if notification.get('method') == 'windowsSandbox/setupCompleted':
            break
    after = request(4, 'windowsSandbox/readiness', None)
    report = {'before': before, 'started': started, 'completed': notification, 'after': after}
    Path('verification/probe-sandbox-update.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)
    assert notification['params']['success'], report
finally:
    process.terminate()
    process.wait(timeout=10)
