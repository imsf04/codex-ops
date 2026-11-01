"""Read native host configuration without creating a chat."""
import json
import os
import queue
import shutil
import subprocess
import threading
from native_cli import native_cli


def call(method, params, env=None, cwd=None):
    process = subprocess.Popen([native_cli(), 'app-server', '--stdio'], env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, encoding='utf-8', cwd=cwd, creationflags=subprocess.CREATE_NO_WINDOW)
    inbox = queue.Queue()
    def read():
        for line in process.stdout:
            inbox.put(json.loads(line))
    threading.Thread(target=read, daemon=True).start()
    def request(id, method, params):
        process.stdin.write(json.dumps({'id': id, 'method': method, 'params': params}) + '\n')
        process.stdin.flush()
        while True:
            message = inbox.get(timeout=45)
            if message.get('id') == id:
                return message
    try:
        request(1, 'initialize', {'clientInfo': {'name': 'codex-ops-verification', 'version': '0.1.0'},
                                  'capabilities': {'experimentalApi': True}})
        process.stdin.write('{"method":"initialized"}\n')
        process.stdin.flush()
        return request(2, method, params)
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == '__main__':
    import sys
    print(json.dumps(call(sys.argv[1], json.loads(sys.argv[2]), os.environ), ensure_ascii=False))
