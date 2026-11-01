"""Explicit reference-to-current comparisons; never infer retained model context."""
import difflib
import json

from workflow_validation import callback, identity, integer, options, require, text


def _request(item):
    options(item, ('path', 'offset', 'limit'))
    return {'path': text(item.get('path'), 'path', 4096),
            'offset': integer(item, 'offset', 1, 10000000, 1),
            'limit': integer(item, 'limit', 1, 300, 100)}


def _requests(args):
    rows = args.get('files')
    require(isinstance(rows, list) and 1 <= len(rows) <= 8, 'incremental requires 1..8 file ranges')
    requests = [_request(row) for row in rows]
    encoded = [json.dumps(row, sort_keys=True) for row in requests]
    require(len(set(encoded)) == len(encoded), 'Duplicate file ranges are not supported')
    return requests


def _baseline(ref, load, root, context, requests):
    if ref is None:
        return None
    text(ref, 'baselineRef', 256)
    value = callback(load, 'load')(ref)
    require(isinstance(value, dict) and value.get('kind') == 'workflow-snapshot', 'Reference is not an incremental snapshot')
    require(value.get('scope') == identity(context) and value.get('root') == root, 'Snapshot belongs to a different session or root')
    require(value.get('requests') == requests, 'Snapshot file ranges differ; start a new baseline')
    return value


def _lines(item):
    return [row['text'] for row in item.get('items', []) if 'text' in row]


def _change(tag, a1, a2, b1, b2, before, after):
    old_rows, new_rows = before.get('items', []), after.get('items', [])
    return {'kind': tag, 'oldRange': {'startIndex': a1, 'endIndex': a2},
            'newRange': {'startIndex': b1, 'endIndex': b2},
            'oldLines': [row.get('line') for row in old_rows[a1:a2]],
            'lines': new_rows[b1:b2]}


def _changes(before, after):
    matcher = difflib.SequenceMatcher(None, _lines(before), _lines(after), autojunk=False)
    return [_change(tag, a1, a2, b1, b2, before, after)
            for tag, a1, a2, b1, b2 in matcher.get_opcodes() if tag != 'equal']


def _delta(before, after):
    changes = _changes(before, after)
    metadata = {key: value for key, value in after.items() if key != 'items'}
    return {**metadata, 'mode': 'delta', 'baselineRevision': before.get('revision'),
            'sameFileRevision': before.get('revision') == after.get('revision'), 'changes': changes,
            'omittedUnchangedLines': len(_lines(after)) - sum(len(change['lines']) for change in changes)}


def _usable(item):
    return isinstance(item, dict) and 'revision' in item and isinstance(item.get('items'), list)


def _item(index, current, baseline):
    before = baseline[index] if index < len(baseline) else None
    if _usable(before) and _usable(current):
        return _delta(before, current)
    return {**current, 'mode': 'full', 'comparisonAvailable': False}


def run(root, args, context, invoke, load, save):
    options(args, ('files', 'baselineRef'))
    requests = _requests(args)
    baseline = _baseline(args.get('baselineRef'), load, root, context, requests)
    writer = callback(save, 'save')
    current = invoke(root, 'read', {'files': requests})
    snapshot = {'kind': 'workflow-snapshot', 'scope': identity(context), 'root': root,
                'requests': requests, 'result': current}
    reference = writer(snapshot)
    previous = baseline['result'].get('items', []) if baseline else []
    items = [_item(index, item, previous) for index, item in enumerate(current.get('items', []))]
    metadata = {key: value for key, value in current.items() if key != 'items'}
    return {**metadata, 'operation': 'incremental', 'effectState': 'none', 'items': items,
            'snapshotRef': reference, 'baselineRef': args.get('baselineRef'),
            'comparisonScope': 'requested windows only; changes elsewhere are not inferred',
            'contextRetentionAssumed': False,
            'nextAction': 'Use snapshotRef at /result for full current evidence. Reuse it as baselineRef only for these exact file ranges.'}
