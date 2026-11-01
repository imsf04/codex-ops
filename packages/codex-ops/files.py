"""Read-only adapter for the unchanged dsh-ops native worker."""
import json
import os
from pathlib import Path
import subprocess
import uuid
import math
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

from store import error
import query_workflow
import native_process

TOOLS = {'read': 'read_files', 'grep': 'grep', 'glob': 'glob', 'stat': 'stat', 'diff': 'diff',
         'inspect': 'inspect_local_file', 'read_table': 'read_table',
         'read_docx': 'read_docx', 'read_pdf': 'read_pdf'}


class _PathRestricted(ValueError):
    pass


class _ArgumentError(ValueError):
    pass


def _root(root):
    base = Path(root)
    if not base.is_absolute() or not base.is_dir():
        return None
    return base.resolve()


def _prepare_paths(base, operation, args):
    entries = _entries(operation, args)
    for entry in entries:
        path = _path(entry)
        path = path if path.is_absolute() else base / path
        if not path.resolve().is_relative_to(base):
            raise _PathRestricted('Requested path leaves the explicitly selected root')
        # Preserve lexical components so the worker can reject links/reparse points.
        entry['path'] = str(path)


def _entries(operation, args):
    if not isinstance(args, dict):
        raise _ArgumentError('args must be an object; use ops_catalog for the selected operation')
    entries = args.get('files', []) if operation == 'read' else [args]
    if not isinstance(entries, list) or not 1 <= len(entries) <= 32:
        raise _ArgumentError('read requires files: a list of 1..32 file request objects')
    return entries


def _path(entry):
    if not isinstance(entry, dict):
        raise _ArgumentError('Each file request must be an object with a path; use ops_catalog("read")')
    value = entry.get('path', '.')
    if not isinstance(value, str):
        raise _ArgumentError('path must be a string')
    return Path(value)


def _invoke_worker(base, operation, args, timeout_seconds=32):
    timeout_seconds = _timeout(timeout_seconds)
    worker = Path(os.environ.get('CODEX_OPS_WORKER', str(Path(__file__).parent / 'bin/dsh-ops-worker.exe')))
    envelope = {'version': 1, 'requestId': uuid.uuid4().hex, 'component': 'file',
                'budget': {'timeoutMs': max(1, min(30000, int((timeout_seconds - 1) * 1000))), 'maxBytes': 131072},
                'request': {'root': str(base), 'scope': 'codex-ops-read', 'read_only': True,
                            'deny_credential_names': True, 'tool': TOOLS[operation], 'args': args}}
    result = native_process.run([str(worker)], json.dumps(envelope).encode(), timeout_seconds, operation)
    if result.returncode:
        return error('WORKER_FAILED', f'Read worker exited {result.returncode}; no files were changed')
    return json.loads(result.stdout)


def _kernel(base, args):
    worker = Path(os.environ.get('CODEX_OPS_KERNEL', str(Path(__file__).parent / 'bin/codex-ops-kernel.exe')))
    envelope = {'version': 1, 'requestId': uuid.uuid4().hex, 'component': 'file',
                'budget': {'timeoutMs': 30000, 'maxBytes': 131072},
                'request': {'root': str(base), 'scope': 'codex-ops-read', 'read_only': True,
                            'deny_credential_names': True, 'tool': 'investigate', 'args': args}}
    try:
        result = native_process.run([str(worker)], json.dumps(envelope).encode(), 32, 'investigate')
        if result.returncode:
            return error('WORKER_FAILED', f'Read kernel exited {result.returncode}; no files were changed')
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError, TypeError) as exc:
        return _worker_error(exc)


def _timeout(value):
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Worker timeout must be finite seconds')
    if not 1 < value <= 32:
        raise ValueError('Worker timeout must be greater than 1 and at most 32 seconds')
    return value


def _worker_error(exc):
    if isinstance(exc, _ArgumentError):
        return error('INVALID_ARGUMENT', str(exc))
    if isinstance(exc, _PathRestricted):
        return error('PATH_RESTRICTED', str(exc))
    if isinstance(exc, subprocess.TimeoutExpired):
        return error('WORKER_TIMEOUT', f'Read exceeded its {exc.timeout:g} second worker budget; narrow the request')
    return error('WORKER_ERROR', str(exc))


def _single(base, operation, args, timeout_seconds=32):
    args = json.loads(json.dumps(args))
    try:
        _prepare_paths(base, operation, args)
        if timeout_seconds == 32:
            return _invoke_worker(base, operation, args)
        return _invoke_worker(base, operation, args, timeout_seconds)
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
            futures = [pool.submit(copy_context().run, _single, base, entry['operation'], entry['args'])
                       for entry in requests]
            results = [future.result() for future in futures]
        return _batch_result(requests, results)
    except (ValueError, TypeError, KeyError) as exc:
        return error('INVALID_ARGUMENT', str(exc))


def run(root, operation, args):
    if operation not in (*TOOLS, 'batch', 'search', 'investigate'):
        return error('INVALID_ARGUMENT', 'Unknown read operation; use ops_catalog for exact schemas and examples')
    base = _root(root)
    if base is None:
        return error('INVALID_ARGUMENT', 'root must be an existing absolute directory')
    if operation == 'investigate':
        return _kernel(base, args)
    if operation == 'batch':
        return _batch(base, args)
    if operation == 'search':
        return query_workflow.run(str(base), args, lambda op, value, timeout: _single(base, op, value, timeout))
    return _single(base, operation, args)
