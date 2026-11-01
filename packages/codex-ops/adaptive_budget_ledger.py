"""Best-effort same-chat reference reread proxy, never a savings measurement."""
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import time
import adaptive_budget
from store import default_root
from task_cost import CHAT

SCHEMA = '''CREATE TABLE IF NOT EXISTS evidence_budget (
 context TEXT NOT NULL, ref TEXT NOT NULL, shown REAL NOT NULL, reread INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(context,ref))'''


def _identity(context):
    if not isinstance(context, str) or CHAT.fullmatch(context) is None:
        return None
    return hashlib.sha256(context.encode()).hexdigest()


def _path(root):
    return (Path(root) if root is not None else default_root()) / 'evidence-budget.sqlite3'


def _write(action, ref, context, root, now):
    identity = _identity(context)
    if identity is None or not isinstance(ref, str):
        return False
    path = _path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=0.1)) as db, db:
            db.execute(SCHEMA)
            _change(db, action, ref, identity, now)
        return True
    except (OSError, sqlite3.Error):
        return False


def _change(db, action, ref, identity, now):
    db.execute('DELETE FROM evidence_budget WHERE shown < ?', (now - 86400,))
    if action == 'show':
        db.execute('INSERT OR IGNORE INTO evidence_budget(context,ref,shown) VALUES(?,?,?)', (identity, ref, now))
    else:
        db.execute('UPDATE evidence_budget SET reread=1 WHERE context=? AND ref=? AND shown BETWEEN ? AND ?',
                   (identity, ref, now - 30, now))
    db.execute('DELETE FROM evidence_budget WHERE rowid NOT IN (SELECT rowid FROM evidence_budget ORDER BY shown DESC LIMIT 2048)')


def record_presentation(ref, context, root=None, now=None):
    return _write('show', ref, context, root, time.time() if now is None else now)


def record_retrieval(ref, context, view='raw', root=None, now=None):
    if view != 'raw':
        return False
    return _write('retrieve', ref, context, root, time.time() if now is None else now)


def budget(context, base=12288, root=None, now=None):
    try:
        rows = _recent(context, root, time.time() if now is None else now)
    except (OSError, sqlite3.Error):
        rows = []
    events = [{'origin': 'production', 'chatId': context, 'attributed': True,
               'reason': 'presentation', 'immediateReread': bool(row[0])} for row in rows]
    result = adaptive_budget.recommend(events, base)
    result['qualification'] = 'Suspected immediate raw reread; explicit full-text requests can also cause this proxy.'
    return result


def _recent(context, root, now):
    identity, path = _identity(context), _path(root)
    if identity is None or not path.exists():
        return []
    with closing(sqlite3.connect(path, timeout=0.1)) as db:
        return db.execute('SELECT reread FROM evidence_budget WHERE context=? AND shown BETWEEN ? AND ?',
                          (identity, now - 300, now)).fetchall()
