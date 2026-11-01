"""Compile staged operations against an in-memory tree, without workspace writes."""
from . import task_tree as tree
from .paths import MAX_BYTES, digest, require, root_path
from .planning import FIELDS, _content, encoded

DIRECTORIES = {'mkdir': {'path'}, 'rmdir': {'path'}, 'copy_tree': {'path', 'to'},
               'move_tree': {'path', 'to'}, 'remove_tree': {'path'}}


def entries(root, stages):
    require(isinstance(stages, list) and 1 <= len(stages) <= 16, 'Use 1-16 ordered stages')
    result = []
    for index, stage in enumerate(stages):
        require(isinstance(stage, list) and 1 <= len(stage) <= 32, 'Each stage needs 1-32 operations')
        result.extend(_entry(root, entry, index) for entry in stage)
    require(len(result) <= 64, 'Task is limited to 64 requested operations')
    _aliases(result)
    return result


def _aliases(entries):
    spellings = {}
    for entry in entries:
        for key in ('path', 'to'):
            if key in entry['args']:
                name = entry['args'][key]
                require(spellings.setdefault(name.casefold(), name) == name, 'Use one spelling for each Windows task path')


def _entry(root, entry, stage):
    require(isinstance(entry, dict) and set(entry) == {'operation', 'args'}, 'Expected operation and args')
    operation, args = entry['operation'], entry['args']
    fields = {**FIELDS, **DIRECTORIES}
    require(isinstance(operation, str) and operation in fields and isinstance(args, dict), 'Unknown task operation')
    require(set(args) == fields[operation], 'Task arguments must match the operation schema')
    args = dict(args)
    for key in ('path', 'to'):
        if key in args:
            args[key] = tree.path(root, args[key])
    return {'operation': operation, 'args': args, 'stage': stage}


def _parent(root, values, name):
    from pathlib import Path
    parent = Path(name).parent.as_posix()
    if parent == '.':
        return
    present = values.get(parent, 'directory' if (root / parent).is_dir() else None)
    require(present == 'directory', 'Parent must exist before its dependent operation')


def _file(root, values, entry, roots):
    operation, args = entry['operation'], entry['args']
    name = args['path']
    original = values.get(name)
    require(original != 'directory', 'File operation cannot target a directory')
    _parent(root, values, name)
    before = {name: digest(original)}
    if operation in ('write', 'edit', 'replace'):
        content = _content(operation, args, original).encode('utf-8')
        require(len(content) <= MAX_BYTES, 'Task file exceeds 1 MiB')
        after = tree.changed(values, name, content, roots)
        return _step(entry, before, after, content.decode('utf-8'))
    return _transfer(root, values, entry, roots, original, before)


def _transfer(root, values, entry, roots, original, before):
    operation, args = entry['operation'], entry['args']
    name = args['path']
    require(isinstance(original, bytes), 'Task source file must exist')
    if operation == 'remove':
        return _step(entry, before, tree.changed(values, name, None, roots))
    dest = args['to']
    _parent(root, values, dest)
    require(name.casefold() != dest.casefold() and values.get(dest) is None, 'Destination must be absent and different')
    before[dest] = 'absent'
    after = tree.changed(values, dest, original, roots)
    after[name] = digest(original)
    if operation == 'move':
        after.update(tree.changed(values, name, None, roots))
    return _step(entry, before, after)


def _step(entry, before, after, content=None):
    return {**entry, 'before': before, 'after': after, 'content': content}


def _directory(root, values, entry, roots):
    name, operation = entry['args']['path'], entry['operation']
    _parent(root, values, name)
    current = values.get(name)
    if operation == 'mkdir':
        require(current is None, 'mkdir requires an absent directory')
        after = tree.changed(values, name, 'directory', roots)
    else:
        require(current == 'directory' and tree.empty(values, name), 'rmdir requires an empty directory')
        after = tree.changed(values, name, None, roots)
    before = {name: 'directory' if current == 'directory' else 'absent'}
    return _step(entry, before, after)


def _expanded(entry, values):
    operation, args, stage = entry['operation'], entry['args'], entry['stage']
    name = args['path']
    require(values.get(name) == 'directory', 'Tree source must be an existing directory')
    members = _members(values, name)
    steps = []
    if operation != 'remove_tree':
        dest = _destination(values, name, args['to'])
        steps.extend(_copy_entry(key, name, dest, values[key], stage) for key in members)
    if operation != 'copy_tree':
        steps.extend(_remove_entry(key, values[key], stage) for key in reversed(members))
    return steps


def _members(values, name):
    matches = (key for key in values if key == name or key.startswith(name + '/'))
    return sorted(matches, key=lambda key: (key.count('/'), key))


def _destination(values, name, dest):
    require(not dest.casefold().startswith(name.casefold() + '/') and not name.casefold().startswith(dest.casefold() + '/'), 'Tree paths overlap')
    require(name.casefold() != dest.casefold() and values.get(dest) is None, 'Tree destination must be absent')
    return dest


def _copy_entry(name, source, dest, value, stage):
    target = dest + name[len(source):]
    operation = 'mkdir' if value == 'directory' else 'copy'
    args = {'path': target} if operation == 'mkdir' else {'path': name, 'to': target}
    return {'operation': operation, 'args': args, 'stage': stage}


def _remove_entry(name, value, stage):
    return {'operation': 'rmdir' if value == 'directory' else 'remove', 'args': {'path': name}, 'stage': stage}


def _compile(root, values, requested, roots):
    result = []
    for entry in requested:
        expanded = _expanded(entry, values) if entry['operation'].endswith('_tree') else [entry]
        for item in expanded:
            handler = _directory if item['operation'] in ('mkdir', 'rmdir') else _file
            result.append(handler(root, values, item, roots))
            require(len(result) <= 256 and len(values) <= tree.MAX_NODES, 'Expanded task exceeds its step/node bound')
    return result


def plan(root, stages, owner=None):
    root = root_path(root)
    requested = entries(root, stages)
    roots = tree.selected([value for entry in requested for key, value in entry['args'].items() if key in ('path', 'to')])
    values = tree.capture(root, roots)
    initial = tree.revisions(values)
    steps = _compile(root, values, requested, roots)
    body = {'kind': 'task-plan', 'version': 1, 'root': str(root), 'roots': roots,
            'initial': initial, 'final': tree.revisions(values), 'stages': stages, 'steps': steps,
            'owner': owner}
    require(len(encoded(body)) <= 8 * MAX_BYTES, 'Task plan exceeds 8 MiB')
    return {**body, 'planDigest': digest(encoded(body))}


def validate(value):
    _envelope(value)
    body = {key: val for key, val in value.items() if key != 'planDigest'}
    require(value.get('planDigest') == digest(encoded(body)), 'Task plan digest mismatch')
    require(1 <= len(value['steps']) <= 256 and len(value['roots']) <= tree.MAX_NODES, 'Invalid task plan bounds')
    root = root_path(value['root'])
    entries(root, value['stages'])
    for name in set(value['initial']) | set(value['final']):
        require(tree.path(root, name) == name, 'Task paths must be normalized')
    return root


def _envelope(value):
    require(isinstance(value, dict), 'Invalid task plan')
    require(value.get('kind') == 'task-plan' and value.get('version') == 1, 'Invalid task plan')
    require(set(value) == {'kind', 'version', 'root', 'roots', 'initial', 'final', 'stages', 'steps', 'owner', 'planDigest'}, 'Invalid task fields')
