"""Bounded, payload-free source attribution and reference retrieval accounting."""
import hashlib
import re
import telemetry_windows

UNATTRIBUTED = 'unattributed'
MAX_DIMENSIONS = 256
MAX_REFERENCES = 2048
MAX_PAGES = 4096
RETENTION_SECONDS = 30 * 24 * 3600
SCHEMA = '''
CREATE TABLE IF NOT EXISTS detail_counts (
 instance_id TEXT NOT NULL, origin TEXT NOT NULL, tool TEXT NOT NULL, session TEXT NOT NULL,
 items INTEGER NOT NULL, original_bytes INTEGER NOT NULL, presented_bytes INTEGER NOT NULL,
 PRIMARY KEY(instance_id,origin,tool,session),
 FOREIGN KEY(instance_id,origin) REFERENCES instances(instance_id,origin) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS reference_sources (
 ref TEXT NOT NULL, origin TEXT NOT NULL, tool TEXT NOT NULL, session TEXT NOT NULL, updated REAL NOT NULL,
 PRIMARY KEY(ref,origin));
CREATE TABLE IF NOT EXISTS retrieval_pages (
 page TEXT NOT NULL, origin TEXT NOT NULL, updated REAL NOT NULL,
 PRIMARY KEY(page,origin));
CREATE TABLE IF NOT EXISTS retrieval_counts (
 instance_id TEXT NOT NULL, origin TEXT NOT NULL, tool TEXT NOT NULL, session TEXT NOT NULL,
 items INTEGER NOT NULL, returned_bytes INTEGER NOT NULL, repeated_items INTEGER NOT NULL,
 repeated_bytes INTEGER NOT NULL, linked_items INTEGER NOT NULL,
 PRIMARY KEY(instance_id,origin,tool,session),
 FOREIGN KEY(instance_id,origin) REFERENCES instances(instance_id,origin) ON DELETE CASCADE);
'''


def digest(value):
    return hashlib.sha256(value.encode('utf-8', errors='surrogatepass')).hexdigest()


def context(value):
    value = value if isinstance(value, dict) else {}
    tool, session = value.get('tool'), value.get('session')
    tool = tool if isinstance(tool, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', tool) else UNATTRIBUTED
    session = digest(session) if isinstance(session, str) and 0 < len(session) <= 1024 else UNATTRIBUTED
    return tool, session


def ref_digest(ref):
    if not isinstance(ref, str) or not re.fullmatch(r'ops://[a-f0-9]{48}', ref):
        raise ValueError('Expected a valid ops reference')
    return digest(ref)


def _dimensions(db, table, identity, labels):
    # Table names are internal constants, never tool inputs.
    found = db.execute(f'SELECT 1 FROM {table} WHERE instance_id=? AND origin=? AND tool=? AND session=?',
                       (*identity, *labels)).fetchone()
    size = db.execute(f'SELECT COUNT(*) FROM {table} WHERE instance_id=? AND origin=?', identity).fetchone()[0]
    return labels if found or size < MAX_DIMENSIONS else (UNATTRIBUTED, UNATTRIBUTED)


def record(db, identity, labels, before, after):
    labels = _dimensions(db, 'detail_counts', identity, labels)
    db.execute('''INSERT INTO detail_counts VALUES (?,?,?,?,1,?,?)
      ON CONFLICT(instance_id,origin,tool,session) DO UPDATE SET items=items+1,
      original_bytes=original_bytes+excluded.original_bytes,
      presented_bytes=presented_bytes+excluded.presented_bytes''', (*identity, *labels, before, after))


def _prune(db, table, origin, now, bound):
    db.execute(f'DELETE FROM {table} WHERE updated < ?', (now - RETENTION_SECONDS,))
    db.execute(f'''DELETE FROM {table} WHERE rowid IN (
      SELECT rowid FROM {table} WHERE origin=? ORDER BY updated DESC,rowid DESC LIMIT -1 OFFSET ?)''',
      (origin, bound))


def link(db, origin, ref, labels, now):
    ref = ref_digest(ref)
    labels = _link_labels(db, origin, ref, labels)
    db.execute('''INSERT INTO reference_sources VALUES (?,?,?,?,?)
      ON CONFLICT(ref,origin) DO UPDATE SET tool=excluded.tool,session=excluded.session,updated=excluded.updated''',
      (ref, origin, *labels, now))
    _prune(db, 'reference_sources', origin, now, MAX_REFERENCES)


def _link_labels(db, origin, ref, labels):
    row = db.execute('SELECT tool,session FROM reference_sources WHERE ref=? AND origin=?', (ref, origin)).fetchone()
    if row is None or tuple(row) == labels:
        return labels
    # Deduplicated observations can have several producers. Ambiguity stays sticky.
    return UNATTRIBUTED, UNATTRIBUTED


def _source(db, origin, ref, fallback, now):
    row = db.execute('SELECT tool,session FROM reference_sources WHERE ref=? AND origin=? AND updated>=?',
                     (ref, origin, now - RETENTION_SECONDS)).fetchone()
    return (tuple(row), 1) if row else (fallback, 0)


def _page(db, origin, ref, page_key, now):
    key = digest(ref + '\0' + page_key)
    repeated = db.execute('SELECT 1 FROM retrieval_pages WHERE page=? AND origin=? AND updated>=?',
                          (key, origin, now - RETENTION_SECONDS)).fetchone() is not None
    db.execute('INSERT INTO retrieval_pages VALUES (?,?,?) ON CONFLICT(page,origin) DO UPDATE SET updated=excluded.updated',
               (key, origin, now))
    _prune(db, 'retrieval_pages', origin, now, MAX_PAGES)
    return int(repeated)


def retrieve(db, identity, ref, returned_bytes, page_key, labels, now):
    ref = ref_digest(ref)
    labels, linked = _source(db, identity[1], ref, labels, now)
    labels = _dimensions(db, 'retrieval_counts', identity, labels)
    repeated = _page(db, identity[1], ref, page_key, now)
    db.execute('''INSERT INTO retrieval_counts VALUES (?,?,?,?,1,?,?,?,?)
      ON CONFLICT(instance_id,origin,tool,session) DO UPDATE SET items=items+1,
      returned_bytes=returned_bytes+excluded.returned_bytes,
      repeated_items=repeated_items+excluded.repeated_items,
      repeated_bytes=repeated_bytes+excluded.repeated_bytes,
      linked_items=linked_items+excluded.linked_items''',
      (*identity, *labels, returned_bytes, repeated, returned_bytes * repeated, linked))
    telemetry_windows.retrieval(db, identity[1], now, labels, returned_bytes, repeated, linked)


def _exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='detail_counts'").fetchone() is not None


def _counts(row):
    return {'items': row['items'], 'originalBytes': row['original'], 'presentedBytes': row['presented'],
            'savedBytes': row['original'] - row['presented']}


def _aggregate(db, origin, cutoff, column):
    rows = db.execute(f'''SELECT {column} AS label, SUM(items) AS items,
      SUM(original_bytes) AS original,SUM(presented_bytes) AS presented
      FROM detail_counts JOIN instances USING(instance_id,origin)
      WHERE origin=? AND updated>=? GROUP BY {column}''', (origin, cutoff)).fetchall()
    return {row['label']: _counts(row) for row in rows}


def _with_legacy(groups, totals):
    accounted = {key: sum(row[key] for row in groups.values()) for key in totals}
    remainder = {key: totals[key] - accounted[key] for key in totals}
    if remainder['items']:
        current = groups.get(UNATTRIBUTED, dict.fromkeys(totals, 0))
        groups[UNATTRIBUTED] = {key: current[key] + remainder[key] for key in totals}
    return groups


def _retrieval_row(row):
    names = ('items', 'returnedBytes', 'repeatedPageItems', 'repeatedPageBytes', 'linkedItems')
    return dict(zip(names, row))


def _retrieval_group(db, origin, cutoff, column):
    rows = db.execute(f'''SELECT {column},SUM(items),SUM(returned_bytes),SUM(repeated_items),
      SUM(repeated_bytes),SUM(linked_items) FROM retrieval_counts JOIN instances USING(instance_id,origin)
      WHERE origin=? AND updated>=? GROUP BY {column}''', (origin, cutoff)).fetchall()
    return {row[0]: _retrieval_row(row[1:]) for row in rows}


def _retrieval(db, origin, cutoff):
    by_tool = _retrieval_group(db, origin, cutoff, 'tool')
    total = _retrieval_row([0] * 5)
    for row in by_tool.values():
        total = {key: total[key] + row[key] for key in total}
    return {**total, 'byTool': by_tool, 'bySession': _retrieval_group(db, origin, cutoff, 'session')}


def empty(totals):
    unattributed = {UNATTRIBUTED: dict(totals)} if totals['items'] else {}
    return {'byTool': dict(unattributed), 'bySession': dict(unattributed),
            'attributionCoverage': {'toolAttributedItems': 0, 'sessionAttributedItems': 0},
            'retrievalCosts': {**_retrieval_row([0] * 5), 'byTool': {}, 'bySession': {}},
            'attributionMeasurement': 'Exact caller-provided native identities only; legacy/unknown events are unattributed; sessions are SHA-256 identifiers',
            'retrievalMeasurement': 'Successful ops_result response UTF-8 bytes at retrieval time; separate from emitted presentation bytes; repeat means same bounded page request, not necessarily avoidable cost'}


def snapshot(db, origin, cutoff, totals):
    output = empty(totals)
    if not _exists(db):
        return output
    for name, column in (('byTool', 'tool'), ('bySession', 'session')):
        output[name] = _with_legacy(_aggregate(db, origin, cutoff, column), totals)
    output['attributionCoverage'] = {
        'toolAttributedItems': totals['items'] - output['byTool'].get(UNATTRIBUTED, {}).get('items', 0),
        'sessionAttributedItems': totals['items'] - output['bySession'].get(UNATTRIBUTED, {}).get('items', 0)}
    output['retrievalCosts'] = _retrieval(db, origin, cutoff)
    return output
