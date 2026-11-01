"""Bounded exact string fragments with JSON pointers; no generated summaries."""
import json

MAX_NODES = 4000
MAX_BYTES = 131072
CHUNK = 1000


def _pointer(parent, key):
    return parent + '/' + str(key).replace('~', '~0').replace('/', '~1')


def _children(value, pointer):
    if isinstance(value, dict):
        return [(_pointer(pointer, key), item) for key, item in value.items()]
    if isinstance(value, list):
        return [(_pointer(pointer, key), item) for key, item in enumerate(value)]
    return []


def _fragment(value, offset, remaining):
    raw = value[offset:offset + CHUNK].encode('utf-8')
    return raw[:remaining].decode('utf-8', errors='ignore')


def _strings(value, pointer, remaining):
    rows, offset = [], 0
    while offset < len(value) and remaining > 0:
        part = _fragment(value, offset, remaining)
        if not part:
            break
        rows.append({'pointer': pointer, 'offset': offset, 'text': part})
        offset += len(part)
        remaining -= len(part.encode('utf-8'))
    return rows, remaining, offset == len(value)


def _continue(pending, visited, remaining):
    return bool(pending) and visited < MAX_NODES and remaining > 0


def flatten(value):
    pending, rows, visited = [('', value)], [], 0
    remaining, strings_complete = MAX_BYTES, True
    while _continue(pending, visited, remaining):
        pointer, item = pending.pop()
        visited += 1
        if isinstance(item, str):
            parts, remaining, done = _strings(item, pointer, remaining)
            rows.extend(parts)
            strings_complete = strings_complete and done
        pending.extend(reversed(_children(item, pointer)))
    return rows, {'scanComplete': not pending and strings_complete,
                  'nodesScanned': visited, 'indexedBytes': MAX_BYTES - remaining}


def fingerprint(value):
    import hashlib
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()
