"""Fixed worker invocation, used only by the native-shell mutation CLI."""
import json
import os
from pathlib import Path
import subprocess
import uuid
from .paths import Conflict, require, target


def invoke(root, tool, args, internal=False):
    args = dict(args)
    for key in ('path', 'to'):
        if key in args:
            args[key] = str(target(root, args[key], internal))
    envelope = {'version': 1, 'requestId': uuid.uuid4().hex, 'component': 'file',
                'budget': {'timeoutMs': 30000, 'maxBytes': 131072},
                'request': {'root': str(root), 'scope': 'codex-ops-native-mutations', 'read_only': False,
                            'write_roots': [str(root)], 'deny_credential_names': True, 'tool': tool, 'args': args}}
    worker = Path(__file__).resolve().parents[1] / 'bin/dsh-ops-worker.exe'
    run = subprocess.run([str(worker)], input=json.dumps(envelope).encode('utf-8'), capture_output=True,
                         timeout=32, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    require(run.returncode == 0, 'Native worker failed; inspect journal postconditions')
    value = json.loads(run.stdout)
    if value.get('status') == 'error':
        raise Conflict(json.dumps(value.get('error', value), ensure_ascii=False))
    return value
