"""Read-only adapter for the unchanged dsh-ops native worker."""
import json
import os
from pathlib import Path
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor

from store import error

TOOLS = {'read': 'read_files', 'grep': 'grep', 'glob': 'glob', 'stat': 'stat', 'diff': 'diff',
         'inspect': 'inspect_local_file', 'read_table': 'read_table',
         'read_docx': 'read_docx', 'read_pdf': 'read_pdf'}


class _PathRestricted(ValueError):
    pass


def _root(root):
    base = Path(root)
    if not base.is_absolute() or not base.is_dir():
        return None
    return base.resolve()


def _prepare_paths(base, operation, args):
    entries = args.get('files', []) if operation == 'read' else [args]
    for entry in entries:
        path = Path(entry.get('path', '.'))
        path = path if path.is_absolute() else base / path
        if not path.resolve().is_relative_to(base):
            raise _PathRestricted('Requested path leaves the explicitly selected root')
        # Preserve lexical components so the worker can reject links/reparse points.
        entry['path'] = str(path)


def _invoke_worker(base, operation, args):
    worker = Path(os.environ.get('CODEX_OPS_WORKER', str(Path(__file__).parent / 'bin/dsh-ops-worker.exe')))
    envelope = {'version': 1, 'requestId': uuid.uuid4().hex, 'component': 'file',
                'budget': {'timeoutMs': 30000, 'maxBytes': 131072},
                'request': {'root': str(base), 'scope': 'codex-ops-read', 'read_only': True,
                            'deny_credential_names': True, 'tool': TOOLS[operation], 'args': args}}
    result = subprocess.run([str(worker)], input=json.dumps(envelope).encode(), capture_output=True,
                            timeout=32, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        return error('WORKER_FAILED', f'Read worker exited {result.returncode}; no files were changed')
    return json.loads(result.stdout)


def _worker_error(exc):
    if isinstance(exc, _PathRestricted):
        return error('PATH_RESTRICTED', str(exc))
    if isinstance(exc, subprocess.TimeoutExpired):
        return error('WORKER_TIMEOUT', 'Read exceeded 32 seconds; narrow the request')
    return error('WORKER_ERROR', str(exc))


def _single(base, operation, args):
    args = json.loads(json.dumps(args))
    try:
        _prepare_paths(base, operation, args)
        return _invoke_worker(base, operation, args)
    except (subprocess.TimeoutExpired, OSError, ValueError, TypeError, KeyError) as exc:
        return _worker_error(exc)


def _batch_requests(args):
    if not isinstance(args, dict) or set(args) != {'requests'}:
        raise ValueError('batch args must contain only requests')
    requests = args['requests']
    if not isinstance(requests, list) or not 1 <= len(requests) <= 4:
        raise ValueError('batch requires 1-4 independent requests')
    return requests


def _validate_request(entry):
    if not isinstance(entry, dict) or set(entry) != {'operation', 'args'}:
        raise ValueError('Each batch request requires operation and args')
    if entry['operation'] not in TOOLS:
        raise ValueError('Batch operations must be supported read-only operations; nested batch is unavailable')
    if not isinstance(entry['args'], dict):
        raise ValueError('Each batch args value must be an object')
    return entry


def _incomplete_result(result):
    return not isinstance(result, dict) or result.get('status') in ('error', 'partial')


def _batch_result(requests, results):
    items = [{'index': index, 'operation': request['operation'], 'result': value}
             for index, (request, value) in enumerate(zip(requests, results))]
    return {'status': 'partial' if any(_incomplete_result(value) for value in results) else 'completed',
            'requestCount': len(requests), 'requestResultsComplete': True,
            'sourceCompleteness': 'per-result', 'effectState': 'none', 'items': items}


def _batch(base, args):
    try:
        requests = [_validate_request(entry) for entry in _batch_requests(args)]
        # Every worker owns the existing 30s native deadline and 32s watchdog.
        # Four parallel read-only calls fit one 60s MCP invocation, without a queue.
        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            results = list(pool.map(lambda entry: _single(base, entry['operation'], entry['args']), requests))
        return _batch_result(requests, results)
    except (ValueError, TypeError, KeyError) as exc:
        return error('INVALID_ARGUMENT', str(exc))


def run(root, operation, args):
    if operation not in (*TOOLS, 'batch'):
        return error('INVALID_ARGUMENT', 'operation must be read, grep, glob, stat, diff, inspect, read_table, read_docx, read_pdf or batch')
    base = _root(root)
    if base is None:
        return error('INVALID_ARGUMENT', 'root must be an existing absolute directory')
    if operation == 'batch':
        return _batch(base, args)
    return _single(base, operation, args)
