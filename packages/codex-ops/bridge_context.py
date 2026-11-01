"""Version-tested transport attribution; Code Mode sessions are not chat IDs."""
import re

from runtime_bridge.wire import fields

SERVICE = '/codex.code_mode.v1.CodeModeHost/'
TOOLS = {SERVICE + 'Execute': 'functions.exec', SERVICE + 'Wait': 'functions.wait',
         SERVICE + 'OpenSession': 'code_mode.notify'}
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
MAX_REQUEST_BYTES = 16 * 1024 * 1024


def _uuid(value):
    if not isinstance(value, str):
        return None
    return value if UUID.fullmatch(value) else None


def _session(request):
    if len(request) > MAX_REQUEST_BYTES:
        return None
    identities = [item for item in fields(request) if item.number == 1]
    if len(identities) != 1 or identities[0].wire != 2:
        return None
    return _uuid(identities[0].value.decode('utf-8'))


def context(method, request):
    tool = TOOLS.get(method)
    if tool is None:
        return {}
    result = {'tool': tool}
    if method == SERVICE + 'OpenSession':
        return result
    try:
        identity = _session(request)
    except (ValueError, TypeError, UnicodeError):
        identity = None
    if identity is not None:
        result.update(session='code-mode:' + identity, sessionKind='code-mode')
    return result


def _thread(meta):
    value = _uuid(meta.get('threadId'))
    if value is None:
        return None
    turn = meta.get('x-codex-turn-metadata', {})
    if not isinstance(turn, dict) or turn.get('thread_id', value) != value:
        return None
    return value


def _window(meta, thread):
    value = meta.get('windowId')
    if not isinstance(value, str) or not value.startswith(thread + ':'):
        return None
    suffix = value[len(thread) + 1:]
    return value if suffix.isascii() and suffix.isdecimal() and len(suffix) <= 12 else None


def mcp_context(meta, tool):
    """Call only with native request metadata and an endpoint-owned tool name."""
    result = {'tool': tool}
    thread = _thread(meta) if isinstance(meta, dict) else None
    if thread is None:
        return result
    result.update(session='chat:' + thread, sessionKind='chat')
    window = _window(meta, thread)
    if window is not None:
        result['window'] = window
    return result
