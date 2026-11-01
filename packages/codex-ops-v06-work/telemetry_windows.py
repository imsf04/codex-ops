"""Bounded five-minute accounting, separate from legacy instance-lifetime totals."""
BUCKET_SECONDS = 300
RETENTION_SECONDS = 7 * 86400
MAX_DIMENSIONS = 128
MAX_ROWS = 32768
WINDOWS = {'hour': 3600, 'day': 86400, 'week': RETENTION_SECONDS}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS window_counts (
 origin TEXT NOT NULL, bucket INTEGER NOT NULL, tool TEXT NOT NULL, session TEXT NOT NULL,
 channel TEXT NOT NULL, reason TEXT NOT NULL, items INTEGER NOT NULL,
 original_bytes INTEGER NOT NULL, presented_bytes INTEGER NOT NULL,
 retrieval_items INTEGER NOT NULL, returned_bytes INTEGER NOT NULL,
 repeated_items INTEGER NOT NULL, repeated_bytes INTEGER NOT NULL, linked_items INTEGER NOT NULL,
 PRIMARY KEY(origin,bucket,tool,session,channel,reason));
CREATE TABLE IF NOT EXISTS window_state (
 origin TEXT PRIMARY KEY, started REAL NOT NULL, updated REAL NOT NULL, pruned_through REAL NOT NULL);
CREATE TABLE IF NOT EXISTS window_overflow (
 origin TEXT NOT NULL, bucket INTEGER NOT NULL, items INTEGER NOT NULL,
 PRIMARY KEY(origin,bucket));
'''


def interval(window, now):
    if window not in WINDOWS:
        raise ValueError('window must be all, hour, day or week')
    end = int(now // BUCKET_SECONDS) * BUCKET_SECONDS
    return {'selection': window, 'startInclusive': end - WINDOWS[window], 'endExclusive': end,
            'bucketSeconds': BUCKET_SECONDS, 'currentPartialBucketExcluded': True,
            'legacyDataExcluded': True, 'maxRowsPerOrigin': MAX_ROWS}


def _labels(db, origin, bucket, labels):
    found = db.execute('SELECT 1 FROM window_counts WHERE origin=? AND bucket=? AND tool=? AND session=? AND channel=? AND reason=?',
                       (origin, bucket, *labels)).fetchone()
    count = db.execute('SELECT COUNT(*) FROM window_counts WHERE origin=? AND bucket=?', (origin, bucket)).fetchone()[0]
    if found or count < MAX_DIMENSIONS:
        return labels
    db.execute('INSERT INTO window_overflow VALUES (?,?,1) ON CONFLICT(origin,bucket) DO UPDATE SET items=items+1', (origin, bucket))
    return ('unattributed', 'unattributed', 'other', 'other')


def _prune(db, origin, now):
    cutoff = int(now // BUCKET_SECONDS) * BUCKET_SECONDS - RETENTION_SECONDS
    db.execute('DELETE FROM window_counts WHERE bucket < ?', (cutoff,))
    db.execute('DELETE FROM window_overflow WHERE bucket < ?', (cutoff,))
    excess = db.execute('SELECT MAX(bucket) FROM (SELECT bucket FROM window_counts WHERE origin=? ORDER BY bucket DESC,rowid DESC LIMIT -1 OFFSET ?)',
                        (origin, MAX_ROWS)).fetchone()[0]
    if excess is not None:
        db.execute('DELETE FROM window_counts WHERE rowid IN (SELECT rowid FROM window_counts WHERE origin=? ORDER BY bucket DESC,rowid DESC LIMIT -1 OFFSET ?)', (origin, MAX_ROWS))
        db.execute('UPDATE window_state SET pruned_through=MAX(pruned_through,?) WHERE origin=?', (excess + BUCKET_SECONDS, origin))


def _write(db, origin, now, labels, values):
    bucket = int(now // BUCKET_SECONDS) * BUCKET_SECONDS
    labels = _labels(db, origin, bucket, labels)
    db.execute('INSERT INTO window_state VALUES (?,?,?,0) ON CONFLICT(origin) DO UPDATE SET updated=excluded.updated', (origin, now, now))
    db.execute('''INSERT INTO window_counts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(origin,bucket,tool,session,channel,reason) DO UPDATE SET
      items=items+excluded.items,original_bytes=original_bytes+excluded.original_bytes,
      presented_bytes=presented_bytes+excluded.presented_bytes,retrieval_items=retrieval_items+excluded.retrieval_items,
      returned_bytes=returned_bytes+excluded.returned_bytes,repeated_items=repeated_items+excluded.repeated_items,
      repeated_bytes=repeated_bytes+excluded.repeated_bytes,linked_items=linked_items+excluded.linked_items''',
      (origin, bucket, *labels, *values))
    _prune(db, origin, now)


def record(db, origin, now, labels, channel, reason, before, after):
    _write(db, origin, now, (*labels, channel, reason), (1, before, after, 0, 0, 0, 0, 0))


def retrieval(db, origin, now, labels, returned, repeated, linked):
    _write(db, origin, now, (*labels, 'other', 'explicit_retrieval'),
           (0, 0, 0, 1, returned, repeated, returned * repeated, linked))


def _rows(db, origin, bounds, column, retrieval_mode=False):
    sums = 'SUM(retrieval_items),SUM(returned_bytes),SUM(repeated_items),SUM(repeated_bytes),SUM(linked_items)' if retrieval_mode else 'SUM(items),SUM(original_bytes),SUM(presented_bytes)'
    count = 'retrieval_items' if retrieval_mode else 'items'
    selection = column or "'total'"
    group = ' GROUP BY ' + column if column else ''
    sql = f'SELECT {selection},{sums} FROM window_counts WHERE origin=? AND bucket>=? AND bucket<?{group} HAVING SUM({count})>0'
    return db.execute(sql, (origin, bounds['startInclusive'], bounds['endExclusive'])).fetchall()


def _presentation(rows):
    return {row[0]: {'items': row[1], 'originalBytes': row[2], 'presentedBytes': row[3],
                     'savedBytes': row[2] - row[3]} for row in rows}


def _retrieval(rows):
    keys = ('items', 'returnedBytes', 'repeatedPageItems', 'repeatedPageBytes', 'linkedItems')
    return {row[0]: dict(zip(keys, row[1:])) for row in rows}


def empty(bounds):
    return {'available': False, 'window': {**bounds, 'collectionStartedAt': None, 'lastSampleAt': None,
            'historyAvailableForFullInterval': False, 'prunedThrough': None, 'dimensionOverflowItems': 0}}


def _coverage(db, origin, bounds):
    row = db.execute('SELECT started,updated,pruned_through FROM window_state WHERE origin=?', (origin,)).fetchone()
    if row is None:
        return empty(bounds)
    overflow = db.execute('SELECT COALESCE(SUM(items),0) FROM window_overflow WHERE origin=? AND bucket>=? AND bucket<?',
                           (origin, bounds['startInclusive'], bounds['endExclusive'])).fetchone()[0]
    return {'available': True, 'window': {**bounds, 'collectionStartedAt': row[0], 'lastSampleAt': row[1],
            'historyAvailableForFullInterval': max(row[0], row[2]) <= bounds['startInclusive'],
            'prunedThrough': row[2] or None, 'dimensionOverflowItems': overflow}}


def snapshot(db, origin, bounds, base):
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='window_counts'").fetchone()
    result = {**base, **empty(bounds)}
    if exists is None:
        return result
    result.update(_coverage(db, origin, bounds))
    result['totals'] = _presentation(_rows(db, origin, bounds, None)).get('total', base['totals'])
    for key, column in (('byTool', 'tool'), ('bySession', 'session'), ('byChannel', 'channel'), ('byReason', 'reason')):
        result[key] = _presentation(_rows(db, origin, bounds, column))
    costs = _retrieval(_rows(db, origin, bounds, None, True)).get('total', dict.fromkeys(('items', 'returnedBytes', 'repeatedPageItems', 'repeatedPageBytes', 'linkedItems'), 0))
    costs.update(byTool=_retrieval(_rows(db, origin, bounds, 'tool', True)), bySession=_retrieval(_rows(db, origin, bounds, 'session', True)))
    result['retrievalCosts'] = costs
    result['attributionCoverage'] = {name: result['totals']['items'] - result[group].get('unattributed', {}).get('items', 0)
                                    for name, group in (('toolAttributedItems', 'byTool'), ('sessionAttributedItems', 'bySession'))}
    return result
