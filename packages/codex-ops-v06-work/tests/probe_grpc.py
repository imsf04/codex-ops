"""Discover the owned native host's advertised gRPC services over loopback."""
import json
from pathlib import Path
import shutil
import socket
import subprocess

import grpc
from grpc_reflection.v1alpha import reflection_pb2, reflection_pb2_grpc

with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
exe = Path(shutil.which('codex')).with_name('codex-code-mode-host.exe')
process = subprocess.Popen([str(exe), '--listen', f'grpc://127.0.0.1:{port}'],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
channel = grpc.insecure_channel(f'127.0.0.1:{port}')
try:
    grpc.channel_ready_future(channel).result(timeout=8)
    stub = reflection_pb2_grpc.ServerReflectionStub(channel)
    for response in stub.ServerReflectionInfo(iter([reflection_pb2.ServerReflectionRequest(list_services='')]), timeout=5):
        print(response)
except Exception as exc:
    print(type(exc).__name__, str(exc))
finally:
    channel.close()
    process.terminate()
    out, err = process.communicate(timeout=5)
    print(json.dumps({'stdout': out.decode(errors='replace')[:1000], 'stderr': err.decode(errors='replace')[-1000:]}))
