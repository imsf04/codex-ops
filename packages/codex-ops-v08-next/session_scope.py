"""Reference ownership from native request metadata, never model arguments."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import os

from bridge_context import mcp_context

CURRENT = ContextVar('codex_ops_reference_owner', default=None)
PREFIX = 'owner-v1:'
POLICY_KEYS = ('sandbox', 'sandbox_mode', 'auto_review_enabled', 'node_repl_auto_review_required')


def policy(meta):
    turn = meta.get('x-codex-turn-metadata', {}) if isinstance(meta, dict) else {}
    if not isinstance(turn, dict):
        return None
    values = {key: turn[key] for key in POLICY_KEYS if key in turn}
    if not values:
        return None
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def native_owner():
    thread = os.environ.get('CODEX_THREAD_ID', '')
    context = mcp_context({'threadId': thread}, 'native')
    return {'session': context.get('session'), 'nativeExecution': True}


def from_meta(meta, runtime=None):
    context = mcp_context(meta, 'scope')
    return {'session': context.get('session'), 'policy': policy(meta), 'runtime': runtime}


def for_runtime(identifier):
    return {'session': None, 'policy': None, 'runtime': str(identifier)}


@contextmanager
def bind(owner):
    token = CURRENT.set(owner)
    try:
        yield owner
    finally:
        CURRENT.reset(token)


def encode_scope(reason):
    owner = CURRENT.get()
    if owner is None:
        return reason
    return PREFIX + json.dumps({'owner': owner, 'reason': reason}, sort_keys=True, separators=(',', ':'))


def owner_of(scope):
    if not scope.startswith(PREFIX):
        return None
    return json.loads(scope[len(PREFIX):])['owner']


def _same_chat(owner, caller):
    if owner['session'] != caller.get('session'):
        return False
    if caller.get('nativeExecution'):
        return True  # Actual native execution independently enforces its current sandbox.
    return owner.get('policy') == caller.get('policy')


def permitted(scope, caller=None):
    owner = owner_of(scope)
    if owner is None:
        return True  # Existing 0.5 bearer refs remain readable until their original expiry.
    caller = CURRENT.get() if caller is None else caller
    if not caller:
        return False
    if owner.get('session'):
        return _same_chat(owner, caller)
    return bool(owner.get('runtime')) and owner['runtime'] == caller.get('runtime')


def identity(owner):
    return owner.get('session') or ('runtime:' + str(owner.get('runtime') or 'unattributed'))
