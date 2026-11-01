"""Small, strict contracts shared by read-only workflow operations."""
import hashlib
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def options(args, allowed):
    require(isinstance(args, dict), 'args must be an object')
    require(not set(args) - set(allowed), 'Unknown workflow arguments: ' + ', '.join(sorted(set(args) - set(allowed))))
    return args


def integer(args, key, low, high, default):
    value = args.get(key, default)
    require(type(value) is int and low <= value <= high, f'{key} must be an integer in {low}..{high}')
    return value


def text(value, label, maximum, empty=False):
    require(isinstance(value, str), f'{label} must be a string')
    require((empty or bool(value)) and len(value.encode('utf-8')) <= maximum,
            f'{label} must fit {maximum} UTF-8 bytes')
    return value


def root_path(root):
    require(isinstance(root, str), 'root must be an absolute directory')
    path = Path(root)
    require(path.is_absolute() and path.is_dir(), 'root must be an existing absolute directory')
    return str(path.resolve())


def identity(context):
    text(context, 'trusted workflow context', 4096)
    return hashlib.sha256(context.encode('utf-8')).hexdigest()


def callback(value, name):
    require(callable(value), f'{name} callback is required for saved workflow observations')
    return value


def complete(value):
    if value.get('status') != 'completed' or _bounded(value):
        return False
    return all(complete(item) for item in _sources(value))


def _sources(value):
    return [item for item in value.get('items', []) if isinstance(item, dict) and 'status' in item]


def _bounded(value):
    flags = any(value.get(key) is False for key in ('complete', 'pageComplete', 'scanComplete'))
    omissions = any(value.get(key, 0) > 0 for key in ('omitted', 'pending', 'failed', 'skippedFiles'))
    return flags or omissions or value.get('truncated') is True


def coverage(value):
    keys = ('status', 'path', 'complete', 'pageComplete', 'scanComplete', 'truncated',
            'truncatedBy', 'nextOffset', 'nextIndex', 'omitted', 'pending', 'failed',
            'skippedFiles', 'skipReasons', 'nextAction')
    result = {key: value[key] for key in keys if key in value}
    children = [coverage(item) for item in _sources(value)]
    if children:
        result['items'] = children
    return result
