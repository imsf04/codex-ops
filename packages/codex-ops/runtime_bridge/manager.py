"""Owned loopback Code Mode host and relay, started by the native CLI shim."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import tomllib

from grpc_relay import serve


def publish_status(path, value):
    serialized = json.dumps(value, indent=2)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(serialized, encoding='utf-8')
    try:
        os.replace(temporary, path)
    except OSError as error:
        if getattr(error, 'winerror', None) != 17:
            raise
        # MSIX LocalAppData redirection can reject a same-directory rename as
        # cross-device. Readers already ignore partial JSON and retry next time.
        path.write_text(serialized, encoding='utf-8')
        temporary.unlink(missing_ok=True)


def _configuration():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-host', required=True, type=Path)
    args = parser.parse_args()
    if not args.native_host.is_file():
        raise FileNotFoundError('Native Code Mode host is missing')
    digest = hashlib.sha256(args.native_host.read_bytes()).hexdigest()
    allowlist = json.loads(Path(__file__).with_name('validated-host.json').read_text(encoding='utf-8'))
    enabled = digest in allowlist['sha256']
    return args.native_host, digest, enabled


def _status_path(shim_pid):
    status_root = Path(os.environ.get('CODEX_OPS_BRIDGE_STATUS', str(Path(os.environ['LOCALAPPDATA']) / 'CodexOps/bridge')))
    status_root.mkdir(parents=True, exist_ok=True)
    return status_root / f'{shim_pid}.json'


def _stop_event():
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    return stop


def _host_address(native):
    lines = queue.Queue()
    threading.Thread(target=lambda: lines.put(native.stdout.readline()), daemon=True).start()
    address = lines.get(timeout=6).decode().strip()
    if not re.fullmatch(r'http://127\.0\.0\.1:[1-9][0-9]{0,4}', address):
        raise RuntimeError('Native host did not return a loopback gRPC address')
    return address.removeprefix('http://')


@contextmanager
def _native_process(path):
    native = subprocess.Popen([str(path), '--listen', 'grpc://127.0.0.1:0'],
                              stdout=subprocess.PIPE, stderr=sys.stderr, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        yield native, _host_address(native)
    finally:
        if native.poll() is None:
            native.terminate()
        native.wait(timeout=5)


def _status_writer(path, metadata, relay):
    def write(state):
        with relay.lock:
            counters = dict(relay.counts)
        publish_status(path, {**metadata, 'state': state, 'updatedAt': time.time(), 'counters': counters})
    return write


def _heartbeat(native, stop, write):
    while not stop.wait(1):
        if native.poll() is not None:
            raise RuntimeError('Native Code Mode host exited')
        write('ready')
    write('stopped')


def _session(native, path, digest, enabled, started, relay, port, stop):
    ready = f'http://127.0.0.1:{port}'
    shim_pid = int(os.environ['CODEX_OPS_BRIDGE_SHIM_PID'])
    metadata = {'version': 1, 'runtimeVersion': tomllib.loads((Path(__file__).resolve().parents[1] / 'pyproject.toml').read_text())['project']['version'], 'pid': os.getpid(), 'shimPid': shim_pid,
                'nativeHostPid': native.pid, 'startedAt': started, 'address': ready,
                'nativeHost': str(path), 'nativeSha256': digest, 'compressionEnabled': enabled}
    write = _status_writer(_status_path(shim_pid), metadata, relay)
    if not enabled:
        print('Codex Ops: this native host version is not validated; forwarding output unchanged.', file=sys.stderr)
    write('ready')
    print(ready, flush=True)
    _heartbeat(native, stop, write)


def main():
    path, digest, enabled = _configuration()
    stop = _stop_event()
    started = time.time()
    with _native_process(path) as (native, address):
        server, channel, relay, port = serve(address, enabled=enabled)
        try:
            _session(native, path, digest, enabled, started, relay, port, stop)
        finally:
            server.stop(0)
            channel.close()
            relay.close()


if __name__ == '__main__':
    main()
