"""Bounded presentation-only interpretation; never mutate the captured value."""
import json

MAX_JSON_BYTES = 1024 * 1024
MAX_UNWRAPS = 3
STATE_KEYS = ('status', 'isError', 'exit_code', 'session_id', 'error', 'effectState',
              'sourceCompleteness', 'complete', 'truncated', 'coverage', 'continuation',
              'nextOffset', 'hasMore', 'total', 'totalCount', 'matchedItems', 'sourceItems')
SHELL_KEYS = frozenset(('exit_code', 'session_id', 'chunk_id'))


def _decode(text):
    if not isinstance(text, str):
        return text
    if len(text) > MAX_JSON_BYTES or len(text.encode('utf-8')) > MAX_JSON_BYTES:
        return text
    try:
        return json.loads(text)
    except (ValueError, RecursionError):
        return text


def _container(text):
    decoded = _decode(text)
    return decoded if isinstance(decoded, (dict, list)) else text


def _text_blocks(blocks):
    if not isinstance(blocks, list) or not blocks:
        return False
    return all(isinstance(block, dict) and block.get('type') == 'text' for block in blocks)


def _text_payload(blocks):
    values = [_decode(block.get('text', '')) for block in blocks]
    return values[0] if len(values) == 1 else values


def _inline(value):
    if not isinstance(value, dict):
        return value
    if set(value) == {'kind', 'value'} and value.get('kind') == 'inline':
        return value['value']
    return value


def _unwrap(value):
    if isinstance(value, str):
        return _container(value)
    if not isinstance(value, dict):
        return value
    if isinstance(value.get('structuredContent'), (dict, list)):
        return _inline(value['structuredContent'])
    if _text_blocks(value.get('content')):
        return _inline(_text_payload(value['content']))
    return _inline(value)


def _state(value):
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in STATE_KEYS if key in value}


def _metadata(layers):
    layers = [layer for layer in layers if layer]
    result = {}
    for layer in reversed(layers):
        result.update(layer)  # The outer transport remains authoritative.
    if len(layers) > 1:
        result['payloadMetadata'] = layers[1:]
    result.setdefault('sourceCompleteness', 'unknown')
    result.setdefault('effectState', 'unknown')
    return result


def _shell(value):
    if not isinstance(value, dict):
        return False
    return isinstance(value.get('output'), str) and bool(SHELL_KEYS.intersection(value))


def _kind(value):
    if _shell(value):
        return 'shell'
    return 'text' if isinstance(value, str) else 'json'


def analyze(value):
    """Return {value, kind, metadata}; unwrap at most three object/envelope steps.

    Bare scalar JSON strings remain text. MCP text blocks retain their scalar JSON
    contract. Metadata keeps outer authority and exposes nested payload metadata.
    """
    current, layers = value, [_state(value)]
    for _ in range(MAX_UNWRAPS):
        decoded = _unwrap(current)
        if decoded is current:
            break
        current = decoded
        layers.append(_state(current))
    return {'value': current, 'kind': _kind(current), 'metadata': _metadata(layers)}
