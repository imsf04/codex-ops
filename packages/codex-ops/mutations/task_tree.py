"""Bounded explicit trees for task planning and frontier verification."""
from pathlib import Path
import re
from .paths import MAX_BYTES, digest, read, require, root_path, target, _regular_components

MAX_NODES = 128
MAX_TOTAL_BYTES = 8 * MAX_BYTES
RESERVED = '.codex-ops-tasks'
DEVICE = re.compile(r'(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)')


def path(root, name):
    require(isinstance(name, str) and bool(name), 'Expected an explicit relative task path')
    value = Path(name)
    _relative(value)
    require(RESERVED not in [p.lower() for p in value.parts], 'Task journal path is reserved')
    resolved = target(root, name) if (root / value).parent.is_dir() else _future(root, value)
    return resolved.relative_to(root).as_posix()


def _relative(value):
    require(not value.drive and not value.is_absolute() and '..' not in value.parts, 'Task paths must remain relative to root')
    for part in value.parts:
        require(not _ambiguous(part), 'Ambiguous Windows task path')


def _ambiguous(part):
    return ':' in part or part.endswith((' ', '.')) or '\x00' in part or bool(DEVICE.match(part))


def _future(root, value):
    ancestor = root / value
    while not ancestor.parent.exists():
        ancestor = ancestor.parent
    target(root, str(ancestor))
    from .paths import CREDENTIAL
    require(not CREDENTIAL.search(value.as_posix()), 'Protected task path')
    require(not any(p.lower() in ('.dsh-ops', '.codex-ops-mutations') for p in value.parts), 'Reserved task path')
    return root / value


def selected(names):
    result = []
    for name in sorted(set(names), key=lambda s: (len(Path(s).parts), s.casefold())):
        if not any(name.casefold() == old.casefold() or name.casefold().startswith(old.casefold() + '/') for old in result):
            result.append(name)
    return result


def _walk(root, name, values):
    require(len(values) < MAX_NODES, 'Task trees exceed 128 nodes')
    absolute = root / name
    _regular_components(absolute)
    if absolute.is_dir():
        values[name] = 'directory'
        for child in sorted(absolute.iterdir()):
            _walk(root, path(root, child.relative_to(root).as_posix()), values)
    else:
        values[name] = read(absolute)
    require(sum(len(v) for v in values.values() if isinstance(v, bytes)) <= MAX_TOTAL_BYTES, 'Task snapshot exceeds 8 MiB')


def capture(root, roots):
    values = {}
    for name in roots:
        _walk(root, name, values)
    return values


def revisions(values):
    return {name: 'directory' if value == 'directory' else digest(value) for name, value in values.items()}


def observe(root, roots):
    return revisions(capture(root, roots))


def frontier(plan, index):
    state = dict(plan['initial'])
    for step in plan['steps'][:index]:
        state = transition(state, step['after'])
    return state


def transition(state, changes):
    result = dict(state)
    for name, value in changes.items():
        if value is None:
            result.pop(name, None)
        else:
            result[name] = value
    return result


def changed(values, name, value, roots):
    if value is None and name not in roots:
        values.pop(name, None)
        return {name: None}
    values[name] = value
    return {name: 'directory' if value == 'directory' else digest(value)}


def empty(values, name):
    return not any(key.startswith(name + '/') for key in values)
