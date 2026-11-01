"""Owned local code-mode-host process; framed IPC evidence, not a Codex chat."""
import json
from pathlib import Path
import queue
import shutil
import struct
import subprocess
import threading
from native_cli import native_cli


class Host:
    def __init__(self, bridge=False, env=None):
        self.exe = Path(native_cli()).with_name('codex-code-mode-host.exe')
        command = [str(self.exe)]
        if bridge:
            import sys
            command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'experimental/code_mode_bridge.py'), '--upstream', str(self.exe)]
        self.process = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        self.messages = queue.Queue()
        self.stderr = []
        self.frames = []
        def read():
            while True:
                header = self.process.stdout.read(4)
                if not header:
                    self.messages.put({'transportClosed': True})
                    return
                size = struct.unpack('<I', header)[0]
                data = self.process.stdout.read(size)
                frame = json.loads(data)
                self.frames.append(frame)
                self.messages.put(frame)
        def errors():
            for line in self.process.stderr:
                self.stderr.append(line.decode(errors='replace'))
        threading.Thread(target=read, daemon=True).start()
        threading.Thread(target=errors, daemon=True).start()

    def send(self, frame):
        data = json.dumps(frame, ensure_ascii=False).encode()
        self.process.stdin.write(struct.pack('<I', len(data)) + data)
        self.process.stdin.flush()

    def receive(self, timeout=10):
        value = self.messages.get(timeout=timeout)
        if value.get('transportClosed'):
            self.process.wait(timeout=3)
            raise RuntimeError(''.join(self.stderr))
        return value

    def request(self, id, request):
        self.send({'type': 'operation/request', 'id': id, 'request': request})

    def open(self):
        self.send({'type': 'connection/hello', 'supportedVersions': [1], 'requiredCapabilities': [], 'optionalCapabilities': []})
        assert self.receive()['type'] == 'connection/ready'
        self.request(1, {'method': 'session/open', 'sessionId': 'probe'})
        return self.receive()

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)


if __name__ == '__main__':
    host = Host()
    try:
        print(json.dumps(host.open()), flush=True)
        host.request(2, {'method': 'session/execute', 'sessionId': 'probe', 'request': {
            'tool_call_id': 'call_1', 'enabled_tools': [], 'source': 'text({hello:123}); notify("notice");',
            'yield_time_ms': 1000, 'max_output_tokens': 1000}})
        while True:
            frame = host.receive()
            print(json.dumps(frame, ensure_ascii=False), flush=True)
            if frame.get('type') == 'delegate/request':
                host.send({'type': 'delegate/response', 'id': frame['id'], 'result': {'status': 'ok', 'value': {'type': 'notification/delivered'}}})
            if frame.get('type') == 'operation/response' and frame.get('id') == 2:
                break
        for _ in range(12):
            try:
                frame = host.receive(timeout=2)
            except queue.Empty:
                break
            print(json.dumps(frame, ensure_ascii=False), flush=True)
            if frame.get('type') == 'delegate/request':
                host.send({'type': 'delegate/response', 'id': frame['id'], 'result': {'status': 'ok', 'value': {'type': 'notification/delivered'}}})
    finally:
        host.close()
