"""Read an existing observation without creating a directory, database or WAL."""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import time

from store import default_root, TTL
from readonly_snapshot import database


def load(ref, root=None):
    if not isinstance(ref, str) or not re.fullmatch(r'ops://[a-f0-9]{48}', ref):
        raise ValueError('Expected an ops reference')
    base = Path(root) if root is not None else default_root()
    path = base / 'observations.sqlite3'
    try:
        return _read(path, ref)
    except (OSError, sqlite3.Error) as exc:
        raise ValueError('Saved reference is unavailable for read-only access; inspect before retrying execution') from exc


def _read(path, ref):
    with database(path) as copy:
        with closing(sqlite3.connect(copy, timeout=1)) as db:
            row = db.execute('SELECT body,created FROM observations WHERE ref=?', (ref,)).fetchone()
    if row is None or row[1] < time.time() - TTL:
        raise ValueError('Reference expired, was released, or was evicted; inspect any previous execution before replanning')
    return json.loads(row[0])
