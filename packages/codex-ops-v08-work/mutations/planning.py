"""Read-only, deterministic plans. Planning never grants execution permission."""
import json
import re
from .paths import Conflict, MAX_BYTES, digest, read, require, root_path, target

FIELDS = {'write': {'path', 'content'}, 'edit': {'path', 'edits'},
          'replace': {'path', 'oldText', 'newText', 'expectedCount'},
          'copy': {'path', 'to'}, 'move': {'path', 'to'}, 'remove': {'path'}}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _entry(entry):
    require(isinstance(entry, dict) and set(entry) == {'operation', 'args'}, 'Each operation needs operation and args')
    operation, args = entry['operation'], entry['args']
    require(operation in FIELDS and isinstance(args, dict), 'Unknown mutation or invalid args')
    require(set(args) == FIELDS[operation], 'Mutation args must match the documented fields exactly')
    return operation, args


def _text(data):
    require(data is not None, 'This operation requires an existing file')
    try:
        return data.decode('utf-8')
    except UnicodeError as exc:
        raise Conflict('Text mutations require valid UTF-8') from exc


def _span(text, edit):
    require(isinstance(edit, dict) and set(edit) == {'oldText', 'newText'}, 'Edits require oldText and newText')
    old, new = edit['oldText'], edit['newText']
    require(isinstance(old, str) and bool(old) and isinstance(new, str), 'Edits require nonempty oldText and string newText')
    start = text.find(old)
    require(start >= 0 and text.find(old, start + 1) < 0, 'oldText must match exactly once')
    return start, start + len(old), new


def _edit(text, edits):
    require(isinstance(edits, list) and 1 <= len(edits) <= 100, 'Use 1-100 exact edits')
    spans = sorted(_span(text, edit) for edit in edits)
    require(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), 'Edits overlap')
    for start, end, replacement in reversed(spans):
        text = text[:start] + replacement + text[end:]
    return text


def _replace(text, args):
    old, new, count = args['oldText'], args['newText'], args['expectedCount']
    require(isinstance(old, str) and bool(old) and isinstance(new, str), 'Replacement requires nonempty oldText and string newText')
    require(type(count) is int and count > 0, 'expectedCount must be a positive integer')
    require(text.count(old) == count, 'Replacement count differs from expectedCount')
    return text.replace(old, new)


def _content(operation, args, original):
    if operation == 'write':
        require(isinstance(args['content'], str), 'content must be a string')
        if original is not None:
            _text(original)
        return args['content']
    text = _text(original)
    return _edit(text, args['edits']) if operation == 'edit' else _replace(text, args)


def _text_item(operation, args, original, name):
    content = _content(operation, args, original)
    require(len(content.encode('utf-8')) <= MAX_BYTES, 'Proposed content exceeds 1 MiB')
    before, after = digest(original), digest(content.encode('utf-8'))
    return {'operation': operation, 'tool': 'write_file', 'args': {'path': name, 'content': content, 'expectedRevision': before},
            'before': {name: before}, 'after': {name: after}}


def _transfer_item(root, operation, args, original, name):
    require(original is not None, 'Source file does not exist')
    revision = digest(original)
    item = {'operation': operation, 'tool': operation, 'args': {'path': name, 'expectedRevision': revision},
            'before': {name: revision}, 'after': {name: 'absent'}}
    if operation == 'remove':
        return item
    dest = target(root, args['to'])
    require(read(dest) is None, 'Copy/move destination must be absent')
    dest_name = dest.relative_to(root).as_posix()
    item['args']['to'] = dest_name
    item['before'][dest_name], item['after'][dest_name] = 'absent', revision
    if operation == 'copy':
        item['after'][name] = revision
    return item


def _item(root, entry):
    operation, args = _entry(entry)
    path = target(root, args['path'])
    original, name = read(path), path.relative_to(root).as_posix()
    if operation in ('write', 'edit', 'replace'):
        return _text_item(operation, args, original, name)
    return _transfer_item(root, operation, args, original, name)


def plan(root, operations):
    base = root_path(root)
    require(isinstance(operations, list) and 1 <= len(operations) <= 32, 'Plan requires 1-32 independent file operations')
    items = [_item(base, operation) for operation in operations]
    names = [name.casefold() for item in items for name in item['before']]
    require(len(names) == len(set(names)), 'Batch operations must have disjoint source and target paths')
    value = {'version': 1, 'root': str(base), 'items': items}
    require(len(encoded(value)) <= 8 * MAX_BYTES, 'Plan is limited to 8 MiB')
    return {**value, 'planDigest': digest(encoded(value))}


def validate(value):
    require(isinstance(value, dict) and set(value) == {'version', 'root', 'items', 'planDigest'}, 'Invalid plan envelope')
    body = {key: value[key] for key in ('version', 'root', 'items')}
    require(value['version'] == 1 and digest(encoded(body)) == value['planDigest'], 'Plan version or digest mismatch')
    _validate_items(value['items'])
    base = root_path(value['root'])
    for item in value['items']:
        _validate_item(base, item)
    return base


def _validate_items(items):
    require(isinstance(items, list) and 1 <= len(items) <= 32, 'Invalid plan item count')
    names = [name.casefold() for item in items for name in item['before']]
    require(len(names) == len(set(names)), 'Plan paths overlap')


def _validate_item(root, item):
    require(set(item) == {'operation', 'tool', 'args', 'before', 'after'}, 'Invalid plan item')
    require(item['operation'] in FIELDS, 'Unknown plan operation')
    args, before = item['args'], item['before']
    name = args['path']
    require(target(root, name).relative_to(root).as_posix() == name, 'Plan paths must be normalized relative paths')
    revision = args['expectedRevision']
    require(revision == 'absent' or bool(re.fullmatch('[0-9a-f]{64}', revision)), 'Invalid expected revision')
    expected_before, expected_after = _expected_states(root, item)
    require(before == expected_before and item['after'] == expected_after, 'Plan postconditions do not match its operation')


def _expected_states(root, item):
    args, operation = item['args'], item['operation']
    name, revision = args['path'], args['expectedRevision']
    if operation in ('write', 'edit', 'replace'):
        require(item['tool'] == 'write_file' and set(args) == {'path', 'content', 'expectedRevision'}, 'Invalid text publication')
        require(isinstance(args['content'], str) and len(args['content'].encode('utf-8')) <= MAX_BYTES, 'Invalid content')
        return {name: revision}, {name: digest(args['content'].encode('utf-8'))}
    require(item['tool'] == operation and revision != 'absent', 'Invalid transfer publication')
    return _transfer_states(root, operation, args)


def _transfer_states(root, operation, args):
    name, revision = args['path'], args['expectedRevision']
    if operation == 'remove':
        require(set(args) == {'path', 'expectedRevision'}, 'Invalid remove arguments')
        return {name: revision}, {name: 'absent'}
    require(set(args) == {'path', 'to', 'expectedRevision'}, 'Invalid transfer arguments')
    dest = args['to']
    require(target(root, dest).relative_to(root).as_posix() == dest, 'Destination must be a normalized relative path')
    require(name.casefold() != dest.casefold(), 'Transfer destination equals source')
    return {name: revision, dest: 'absent'}, {name: revision if operation == 'copy' else 'absent', dest: revision}


def summary(value):
    return {'status': 'planned', 'effectState': 'none', 'planDigest': value['planDigest'], 'root': value['root'],
            'operationCount': len(value['items']), 'items': [{'operation': item['operation'], 'before': item['before'], 'after': item['after']} for item in value['items']],
            'execution': 'Execute the saved plan through the native shell; this plan grants no permissions'}
