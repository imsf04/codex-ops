"""Best-effort, payload-free accounting of emitted presentation text."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid
import telemetry_details

from store import default_root

RETENTION_SECONDS = 30 * 24 * 3600
MAX_INSTANCES = 128
CHANNELS = frozenset(('text', 'notify', 'wait', 'error', 'other'))
REASONS = frozenset(('compacted', 'progress_unchanged', 'below_threshold', 'not_beneficial',
                    'storage_unavailable', 'storage_limit', 'error_preserved',
                    'already_compact', 'explicit_retrieval', 'frame_repeat', 'disabled', 'other'))
MEASUREMENT = ('Best-effort emitted-text UTF-8 bytes before/after presentation; '
               'includes explicit retrieval, excludes opaque protocol frames; not tokens or net context savings')
SCHEMA = '''
    CREATE TABLE IF NOT EXISTS instances (
        instance_id TEXT NOT NULL, origin TEXT NOT NULL,
        started REAL NOT NULL, updated REAL NOT NULL,
        PRIMARY KEY(instance_id, origin));
    CREATE TABLE IF NOT EXISTS counts (
        instance_id TEXT NOT NULL, origin TEXT NOT NULL,
        channel TEXT NOT NULL, reason TEXT NOT NULL,
        items INTEGER NOT NULL, original_bytes INTEGER NOT NULL, presented_bytes INTEGER NOT NULL,
        PRIMARY KEY(instance_id, origin, channel, reason),
        FOREIGN KEY(instance_id, origin) REFERENCES instances(instance_id, origin) ON DELETE CASCADE);
'''


def _origin(value):
    if value not in ('production', 'validation'):
        raise ValueError('Telemetry origin must be production or validation')
    return value


def _path(root):
    base = Path(root) if root is not None else default_root()
    return base / 'telemetry.sqlite3'


def _connect(root):
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=0.25, check_same_thread=False)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript(SCHEMA + telemetry_details.SCHEMA)
        return db
    except sqlite3.Error:
        db.close()
        raise


def _register(db, instance_id, origin, started, updated):
    db.execute('''INSERT INTO instances VALUES (?,?,?,?)
                  ON CONFLICT(instance_id,origin) DO UPDATE SET updated=excluded.updated''',
               (instance_id, origin, started, updated))


def _prune(db, origin, now):
    db.execute('DELETE FROM instances WHERE updated < ?', (now - RETENTION_SECONDS,))
    db.execute('''DELETE FROM instances WHERE origin=? AND instance_id IN (
                    SELECT instance_id FROM instances WHERE origin=?
                    ORDER BY updated DESC, instance_id DESC LIMIT -1 OFFSET ?)''',
               (origin, origin, MAX_INSTANCES))


def _valid_counts(before, after):
    return all(type(value) is int and value >= 0 for value in (before, after))


def _bounded(value, allowed):
    return value if value in allowed else 'other'


def _close(db):
    if db is not None:
        try:
            db.close()
        except sqlite3.Error:
            pass


class Telemetry:
    def __init__(self, root=None, instance_id=None, origin=None, context=None):
        self.instance_id = instance_id or uuid.uuid4().hex
        selected_origin = os.environ.get('CODEX_OPS_MEASUREMENT_ORIGIN', 'production') if origin is None else origin
        self.origin = _origin(selected_origin)
        self._context = telemetry_details.context(context)
        self.started_at = time.time()
        self.dropped_records = 0
        self._lock = threading.Lock()
        self._db = None
        try:
            self._db = _connect(root)
            with self._db:
                _register(self._db, self.instance_id, self.origin, self.started_at, self.started_at)
                _prune(self._db, self.origin, self.started_at)
        except (OSError, sqlite3.Error):
            _close(self._db)
            self._db = None

    def _unavailable(self):
        self.dropped_records += 1
        return False

    def record(self, channel, reason, before_bytes, after_bytes, context=None):
        if not _valid_counts(before_bytes, after_bytes):
            return self._unavailable()
        labels = self._labels(context)
        return self._write(lambda: self._persist(_bounded(channel, CHANNELS), _bounded(reason, REASONS),
                                                before_bytes, after_bytes, labels))

    def _labels(self, context):
        return self._context if context is None else telemetry_details.context(context)

    def _write(self, callback):
        with self._lock:
            if self._db is None:
                return self._unavailable()
            try:
                callback()
                return True
            except (sqlite3.Error, ValueError, TypeError):
                return self._unavailable()

    def _persist(self, channel, reason, before, after, labels):
        now = time.time()
        with self._db:
            _register(self._db, self.instance_id, self.origin, self.started_at, now)
            self._db.execute('''INSERT INTO counts VALUES (?,?,?,?,1,?,?)
                ON CONFLICT(instance_id,origin,channel,reason) DO UPDATE SET
                    items=items+1, original_bytes=original_bytes+excluded.original_bytes,
                    presented_bytes=presented_bytes+excluded.presented_bytes''',
                (self.instance_id, self.origin, channel, reason, before, after))
            telemetry_details.record(self._db, (self.instance_id, self.origin), labels, before, after)
            _prune(self._db, self.origin, now)

    def _auxiliary(self, callback):
        now = time.time()
        with self._db:
            _register(self._db, self.instance_id, self.origin, self.started_at, now)
            callback(now)
            _prune(self._db, self.origin, now)

    def link_reference(self, ref, context=None):
        labels = self._labels(context)
        return self._write(lambda: self._auxiliary(lambda now:
            telemetry_details.link(self._db, self.origin, ref, labels, now)))

    def record_retrieval(self, ref, returned_bytes, page_key, context=None):
        if not _valid_counts(returned_bytes, 0):
            return self._unavailable()
        if not isinstance(page_key, str) or len(page_key) > 65536:
            return self._unavailable()
        labels = self._labels(context)
        return self._write(lambda: self._auxiliary(lambda now:
            telemetry_details.retrieve(self._db, (self.instance_id, self.origin), ref, returned_bytes,
                                       page_key, labels, now)))

    def close(self):
        with self._lock:
            _close(self._db)
            self._db = None


def _counts(row):
    original, presented = row['original'], row['presented']
    return {'items': row['items'], 'originalBytes': original, 'presentedBytes': presented,
            'savedBytes': original - presented}


def _aggregate(db, origin, cutoff, column=None):
    # Column is selected internally, never read from tool input or payloads.
    selection = column if column else "'total'"
    group = ' GROUP BY ' + column if column else ''
    sql = f'''SELECT {selection} AS label, COALESCE(SUM(items),0) AS items,
              COALESCE(SUM(original_bytes),0) AS original,
              COALESCE(SUM(presented_bytes),0) AS presented
              FROM counts JOIN instances USING(instance_id,origin)
              WHERE origin=? AND updated>=?{group}'''
    rows = db.execute(sql, (origin, cutoff)).fetchall()
    return {row['label']: _counts(row) for row in rows}


def _instances(db, origin, cutoff):
    rows = db.execute('''SELECT instance_id,started,updated FROM instances
                         WHERE origin=? AND updated>=?
                         ORDER BY updated DESC,instance_id DESC LIMIT ?''',
                      (origin, cutoff, MAX_INSTANCES)).fetchall()
    return [{'instanceId': row['instance_id'], 'startedAt': row['started'], 'updatedAt': row['updated']} for row in rows]


def _empty(origin):
    totals = {'items': 0, 'originalBytes': 0, 'presentedBytes': 0, 'savedBytes': 0}
    return {'available': False, 'measurement': MEASUREMENT, 'origin': origin,
            'retentionSeconds': RETENTION_SECONDS, 'maxInstancesPerOrigin': MAX_INSTANCES,
            'totals': totals, 'byChannel': {}, 'byReason': {}, 'instances': [], **telemetry_details.empty(totals)}


def _snapshot(path, origin):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=0.25)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')  # All aggregates come from one consistent read snapshot.
        cutoff = time.time() - RETENTION_SECONDS
        totals = _aggregate(db, origin, cutoff)['total']
        return {**_empty(origin), 'available': True, 'totals': totals,
                'byChannel': _aggregate(db, origin, cutoff, 'channel'), 'byReason': _aggregate(db, origin, cutoff, 'reason'),
                'instances': _instances(db, origin, cutoff), **telemetry_details.snapshot(db, origin, cutoff, totals)}


def snapshot(origin='production', root=None):
    origin = _origin(origin)
    try:
        path = _path(root)
        if path.is_file():
            return _snapshot(path, origin)
    except (OSError, sqlite3.Error):
        pass
    return _empty(origin)
