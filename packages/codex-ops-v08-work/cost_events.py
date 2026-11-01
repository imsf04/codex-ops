"""Payload-free measured workflow and worker events with explicit cohorts."""
from contextlib import contextmanager, closing
from contextvars import ContextVar
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import tomllib

from store import default_root

VERSION = tomllib.loads(Path(__file__).with_name('pyproject.toml').read_text())['project']['version']
CHAT = re.compile(r'chat:[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z')
CURRENT = ContextVar('codex_ops_cost_context', default=(None, None, None))
WRITE_FAILURES = 0
FAILURE_LOCK = threading.Lock()
OPERATIONS = frozenset(('investigate', 'evidence', 'working_set', 'working_set.save', 'verify', 'locate', 'diagnose',
                       'documents', 'incremental', 'sdk', 'read', 'grep', 'glob', 'stat', 'diff',
                       'inspect', 'read_table', 'read_docx', 'read_pdf', 'search', 'compound_search'))
SCHEMA = '''CREATE TABLE IF NOT EXISTS task_events (
 at REAL NOT NULL, version TEXT NOT NULL, origin TEXT NOT NULL, chat TEXT,
 root TEXT, task TEXT, kind TEXT NOT NULL, operation TEXT NOT NULL,
 outcome TEXT NOT NULL, evidence TEXT NOT NULL, reused INTEGER NOT NULL)'''


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest() if isinstance(value, str) else None


def identity(context):
    return _hash(context.lower()) if isinstance(context, str) and CHAT.fullmatch(context) else None


@contextmanager
def scope(context, root, task_id=None):
    token = CURRENT.set((identity(context), _hash(str(root).casefold()), _hash(task_id)))
    try:
        yield
    finally:
        CURRENT.reset(token)


def _origin(origin):
    value = origin or os.environ.get('CODEX_OPS_MEASUREMENT_ORIGIN', 'production')
    return value if value in ('production', 'validation') else 'unknown'


def _path(root):
    return (Path(root) if root is not None else default_root()) / 'task-events.sqlite3'


def _persist(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=0.1)) as db, db:
        db.execute(SCHEMA)
        db.execute('INSERT INTO task_events VALUES (?,?,?,?,?,?,?,?,?,?,?)', row)
        db.execute('DELETE FROM task_events WHERE at < ?', (row[0] - 30 * 86400,))
        db.execute('DELETE FROM task_events WHERE rowid NOT IN '
                   '(SELECT rowid FROM task_events ORDER BY rowid DESC LIMIT 50000)')


def record(kind, operation, outcome='observed', evidence='unknown', reused=False,
           root=None, now=None, origin=None):
    try:
        chat, workspace, task = CURRENT.get()
        row = (time.time() if now is None else now, VERSION, _origin(origin), chat, workspace, task,
               kind, operation if operation in OPERATIONS else 'unknown', outcome, evidence, int(bool(reused)))
        _persist(_path(root), row)
        return True
    except (OSError, sqlite3.Error, TypeError, ValueError):
        _write_failed()
        return False


def _write_failed():
    global WRITE_FAILURES
    with FAILURE_LOCK:
        WRITE_FAILURES += 1


def worker(operation, **options):
    return record('worker-start', operation, **options)


def snapshot(context=None, root=None, since=None, until=None, origin='production', version=None):
    try:
        result = _snapshot(context, root, since, until, origin, version)
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        result = {'available': False, 'reason': str(exc)}
    result['collection'] = {'processId': os.getpid(), 'knownDroppedEvents': WRITE_FAILURES,
                            'scope': 'Current Python process since import; all origins',
                            'complete': False,
                            'reason': 'Other producer processes and retained/pruned records are not proven complete.'}
    return result


def _filters(context, since, until, origin, version):
    terms, values = ['origin=?'], [_origin(origin)]
    for column, operator, value in (('chat', '=', identity(context)), ('at', '>=', since),
                                    ('at', '<', until), ('version', '=', version)):
        if value is not None:
            terms.append(column + operator + '?')
            values.append(value)
    return ' AND '.join(terms), values


def _snapshot(context, root, since, until, origin, version):
    if context is not None and identity(context) is None:
        return {'available': False, 'reason': 'Native chat identity unavailable'}
    path = _path(root)
    if not path.exists():
        return {'available': False, 'reason': 'No measured event ledger'}
    where, values = _filters(context, since, until, origin, version)
    with closing(sqlite3.connect(path, timeout=0.1)) as db:
        rows = db.execute('SELECT version,kind,operation,outcome,evidence,reused,COUNT(*) '
                          'FROM task_events WHERE ' + where + ' GROUP BY 1,2,3,4,5,6', values).fetchall()
    return _summary(rows, since, until, origin, context)


def _summary(rows, since, until, origin, context):
    groups = [dict(zip(('version','kind','operation','outcome','evidence','reused','count'), row)) for row in rows]
    return {'available': True, 'origin': _origin(origin), 'since': since, 'until': until,
            'scope': 'native-chat' if context else 'store', 'groups': groups,
            'workerStarts': sum(row['count'] for row in groups if row['kind'] == 'worker-start'),
            'retention': {'maxDays': 30, 'maxRows': 50000}, 'eligible': None, 'adoptionRate': None,
            'meaning': 'Measured events only. Worker starts, native actions and model calls are distinct. '
                       'No opportunity denominator is inferred; completion and evidence are not task success.'}
