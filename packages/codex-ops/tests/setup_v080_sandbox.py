"""Initialize private acceptance homes through the native sandbox lifecycle API."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from native_cli import native_cli


def setup(version):
    area = Path(os.environ['LOCALAPPDATA']) / 'CodexOps' / 'acceptance-0.8' / version
    home = area / 'home'
    assert (home / 'config.toml').is_file()
    workspace = area / 'sandbox-probe'
    workspace.mkdir(exist_ok=True)
    environment = {**os.environ, 'CODEX_HOME': str(home), 'CODEX_OPS_STORE': str(area / 'setup-store')}
    process = subprocess.Popen([native_cli(), 'app-server', '--stdio'], env=environment, cwd=workspace,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
    inbox = queue.Queue()
    events = []
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
            message = inbox.get(timeout=60)
            if message.get('id') == number:
                return message
            events.append(message)
    try:
        request(1, 'initialize', {'clientInfo': {'name': 'codex-ops-acceptance', 'version': '0.8.0'},
                                 'capabilities': {'experimentalApi': True}})
        send({'method': 'initialized'})
        before = request(2, 'windowsSandbox/readiness', None)
        print(json.dumps({'version': version, 'before': before}), flush=True)
        started = request(3, 'windowsSandbox/setupStart', {'mode': 'elevated', 'cwd': str(workspace)})
        print(json.dumps({'version': version, 'started': started}), flush=True)
        if 'error' in started:
            raise RuntimeError(started)
        deadline = time.monotonic() + 240
        completed = None
        while completed is None and time.monotonic() < deadline:
            completed = next((event for event in events if event.get('method') == 'windowsSandbox/setupCompleted'), None)
            if completed is None:
                events.append(inbox.get(timeout=60))
        after = request(4, 'windowsSandbox/readiness', None)
        record = {'version': version, 'before': before, 'started': started, 'completed': completed, 'after': after}
        (area / 'sandbox-setup.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        print(json.dumps(record), flush=True)
        assert completed and completed['params']['success'], record
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('versions', nargs='+', choices=('0.6.1','0.7.0','0.8.0'))
    options = parser.parse_args()
    for version in options.versions:
        setup(version)
