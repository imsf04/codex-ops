"""Scoped evidence pointers; native revision checks precede exact-file reuse."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import session_scope
from store import ReferenceUnavailable
from workflow_validation import identity

UNAVAILABLE = (ReferenceUnavailable, sqlite3.Error, OSError, ValueError)


def _scope(root, owner):
    if not owner.get('session'):
        return None
    value = [owner['session'], owner.get('policy'), str(Path(root).resolve())]
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


def _query(args):
    return hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()


def _table(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS workflow_memory_v1 '
                     '(scope TEXT, query TEXT, ref TEXT, manifest TEXT, created REAL, PRIMARY KEY(scope,query))')


def _lookup(store, scope, query=None):
    _table(store)
    sql = 'SELECT ref,manifest FROM workflow_memory_v1 WHERE scope=? AND created>=?'
    values = [scope, time.time() - store.ttl]
    if query is not None:
        sql += ' AND query=?'
        values.append(query)
    return store.db.execute(sql + ' ORDER BY created DESC LIMIT 1', values).fetchone()


def _source(row):
    source = row.get('source', {})
    if not isinstance(source, dict):
        return None
    if not source.get('path') or not source.get('revision'):
        return None
    return {'path': source['path'], 'revision': source['revision']}


def sources(value):
    found = {}
    for row in value.get('items', []):
        source = _source(row)
        if source:
            found[source['path']] = source
    return list(found.values())[:8]


def _capture(store, value):
    receipt = store.capture(value, scope='workflow-memory', force=True)
    if receipt.get('kind') != 'reference':
        raise ValueError('Evidence memory could not be saved')
    return receipt['ref']


def _source_snapshot(value, source):
    return {'kind': 'source-evidence', 'items': [row for row in value.get('items', [])
            if row.get('source', {}).get('path') == source['path']],
            'coverage': 'Selected lines for this file only; not the entire file or task.'}


def _manifest(store, root, owner, args, value):
    return {'kind': 'working-set-v1', 'scope': identity(session_scope.identity(owner)),
            'root': root, 'title': args.get('question', ''), 'pending': [],
            'sources': [{'ref': _capture(store, _source_snapshot(value, source)),
                         'label': 'Acquired source evidence', **source}
                        for source in sources(value)]}


def _remember(store, root, owner, args, value):
    scope = _scope(root, owner)
    if not scope or not sources(value):
        return {'state': 'unattributed-or-empty'}
    ref = _capture(store, value)
    manifest = _capture(store, _manifest(store, root, owner, args, value))
    _table(store)
    with store.db:
        store.db.execute('DELETE FROM workflow_memory_v1 WHERE created<?', (time.time() - store.ttl,))
        store.db.execute('INSERT OR REPLACE INTO workflow_memory_v1 VALUES (?,?,?,?,?)',
                         (scope, _query(args), ref, manifest, time.time()))
        store.db.execute('DELETE FROM workflow_memory_v1 WHERE scope=? AND query NOT IN '
                         '(SELECT query FROM workflow_memory_v1 WHERE scope=? ORDER BY created DESC LIMIT 16)',
                         (scope, scope))
    return {'state': 'saved', 'workingSetRef': manifest}


def remember(store, root, owner, args, value):
    try:
        return _remember(store, root, owner, args, value)
    except UNAVAILABLE:
        return {'state': 'unavailable'}


def latest(store, root, owner):
    scope = _scope(root, owner)
    if not scope:
        raise ValueError('Automatic evidence recovery requires a native chat identity')
    row = _lookup(store, scope)
    if not row:
        raise ValueError('No saved source evidence for this chat and root')
    store.get(row[1])
    return row[1]


def _paths(root, paths):
    return {str((Path(root) / path).resolve()) for path in paths}


def _requested_files(root, args):
    requested = args.get('paths', [])
    if not requested or not isinstance(requested, list):
        return None
    return _paths(root, requested)


def _covered_files(root, value, expected):
    stages = value.get('coverage', {}).get('stages', [])
    return bool(stages) and all(_stage_file(root, stage, expected) for stage in stages)


def _strict_files(root, args, value):
    expected = _requested_files(root, args)
    if expected is None:
        return False
    actual = {source['path'] for source in sources(value)}
    if actual != expected:
        return False
    return _covered_files(root, value, expected)


def _stage_file(root, stage, expected):
    path = stage.get('path')
    if not isinstance(path, str):
        return False
    return _paths(root, [path]).issubset(expected)


def _fresh(root, value, invoke):
    known = sources(value)
    result = invoke(root, 'read', {'files': [{'path': source['path'], 'offset': 1, 'limit': 1}
                                          for source in known]})
    rows = result.get('items', [])
    if len(rows) != len(known):
        return False
    expected = {row['path']: row['revision'] for row in known}
    return all(_current(row, expected) for row in rows)


def _current(row, expected):
    return row.get('status') == 'completed' and row.get('revision') == expected.get(row.get('path'), '')


def _reuse(store, root, owner, args, invoke):
    scope = _scope(root, owner)
    if not scope:
        return None
    row = _lookup(store, scope, _query(args))
    if not row:
        return None
    value = store.get(row[0])
    if not _strict_files(root, args, value) or not _fresh(root, value, invoke):
        return None
    return {**value, 'evidenceReuse': {'hit': True, 'revisionsChecked': len(sources(value)),
                                      'workingSetRef': row[1], 'contextRetentionAssumed': False}}


def reuse(store, root, owner, args, invoke):
    try:
        return _reuse(store, root, owner, args, invoke)
    except UNAVAILABLE:
        return None
