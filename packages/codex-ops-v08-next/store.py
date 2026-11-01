"""User-local capability references with transactional quotas and bounded retrieval."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time

from reducers import clip, encode, metadata, payload, preview
import retrieval_views
import query_aggregates
import session_scope

THRESHOLD = 8192
MAX_VALUE = 10 * 1024 * 1024
MAX_STORE = 100 * 1024 * 1024
TTL = 24 * 3600


class ReferenceUnavailable(Exception):
    pass


def _require_owner(scope):
    if not session_scope.permitted(scope):
        raise ReferenceUnavailable('Reference belongs to another native session or permission context.')


def default_root():
    return Path(os.environ.get('CODEX_OPS_STORE', str(Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'CodexOps')))


def error(code, message):
    return {'status': 'error', 'error': {'code': code, 'message': message, 'effectState': 'none'}}


def pointer(value, path):
    if not path:
        return value
    if not path.startswith('/'):
        raise ValueError('path must be an RFC 6901 JSON pointer')
    for part in path[1:].split('/'):
        value = value[_pointer_key(value, part)]
    return value


def _pointer_key(value, token):
    key = token.replace('~1', '/').replace('~0', '~')
    if isinstance(value, list) and key.isdecimal():
        return int(key)
    return key


class _ItemTooLarge(ValueError):
    pass


def _retrieval_error(exc):
    if isinstance(exc, ReferenceUnavailable):
        return error('REFERENCE_UNAVAILABLE', str(exc))
    if isinstance(exc, _ItemTooLarge):
        return error('ITEM_TOO_LARGE', str(exc))
    return error('INVALID_ARGUMENT', str(exc))


def _validate_page(view, offset, limit, max_bytes):
    if view not in ('items', 'raw', 'outline', 'find', 'count', 'group'):
        raise ValueError('Use view items/raw/outline/find/count/group')
    _validate_bounds(offset, limit, max_bytes)
    if view != 'raw' and limit > 200:
        raise ValueError('items/outline/find limit must be 1..200; raw uses max_bytes')


def _validate_bounds(offset, limit, max_bytes):
    if offset < 0 or limit < 1:
        raise ValueError('offset >= 0 and limit >= 1 required')
    if not 512 <= max_bytes <= 16000:
        raise ValueError('max_bytes must be 512..16000')


def _raw_text(raw, remaining):
    if remaining < 16:
        raise ValueError('Page metadata exceeds max_bytes; shorten path or increase budget')
    text = clip(raw, remaining - 12)
    while len(encode(text).encode()) > remaining - 10:
        text = text[:len(text) // 2]
    if raw and not text:
        raise ValueError('Increase max_bytes to retrieve the next character')
    return text


def _item_sequence(value):
    if isinstance(value, list):
        return value
    return value.splitlines() if isinstance(value, str) else [value]


def _contains(item, query):
    return not query or query in (item if isinstance(item, str) else encode(item))


def _project_item(item, fields):
    if not fields:
        return item
    if not isinstance(item, dict):
        raise ValueError('fields projection requires object items')
    return {key: item[key] for key in fields if key in item}


def _continuation(next_offset, total):
    return {'complete': next_offset >= total, 'nextOffset': next_offset if next_offset < total else None}


class _Page:
    """Own a retrieval cursor, projection and byte budget behind Store.result."""
    def __init__(self, ref, view, path, offset, limit, max_bytes, fields, query):
        _validate_page(view, offset, limit, max_bytes)
        self.base = {'ref': ref, 'view': view, 'path': path, 'offset': offset, 'sourceCompleteness': 'unknown'}
        if len(encode(self.base).encode()) + 50 > max_bytes:
            raise ValueError('Page metadata exceeds max_bytes; shorten path or increase budget')
        self.offset, self.limit, self.max_bytes = offset, limit, max_bytes
        self.fields, self.query = fields, query

    def render(self, original):
        result = self._render(original)
        if len(encode(result).encode()) > self.max_bytes:
            raise ValueError('Page metadata exceeds max_bytes; shorten path or increase budget')
        return result

    def _render(self, original):
        if self.base['view'] == 'raw':
            return self._raw(pointer(original, self.base['path']))
        if self.base['view'] in ('outline', 'find'):
            return self._discover(pointer(payload(original), self.base['path']))
        if self.base['view'] in ('count', 'group'):
            return query_aggregates.render(self.base['view'], pointer(payload(original), self.base['path']),
                self.fields, self.query, self.offset, self.limit, self.max_bytes, self.base)
        return self._items(pointer(payload(original), self.base['path']))

    def _discover(self, selected):
        if self.fields:
            raise ValueError('Use items for field projection')
        result = retrieval_views.render(self.base['view'], selected, self.base['path'], self.query,
                                        self.offset, self.limit, self.max_bytes, self.base)
        return result

    def _raw(self, selected):
        if self.fields or self.query:
            raise ValueError('raw view accepts path and character offset; use items for fields/query')
        raw = selected if isinstance(selected, str) else encode(selected)
        base = {**self.base, 'text': '', 'totalCharacters': len(raw), 'offsetUnit': 'unicode-codepoints',
                **_continuation(self.offset, len(raw))}
        remaining = self.max_bytes - len(encode(base).encode())
        text = _raw_text(raw[self.offset:], remaining)
        return {**self.base, 'text': text, 'totalCharacters': len(raw), 'offsetUnit': 'unicode-codepoints',
                **_continuation(self.offset + len(text), len(raw))}

    def _items(self, selected):
        items = _item_sequence(selected)
        matches = [(i, item) for i, item in enumerate(items) if _contains(item, self.query)]
        page = self._records(matches, len(items))
        return self._item_page(matches, len(items), page)

    def _item_page(self, matches, source_count, page):
        return {**self.base, 'items': page, 'matchedItems': len(matches), 'sourceItems': source_count,
                **_continuation(self.offset + len(page), len(matches))}

    def _records(self, matches, source_count):
        page = []
        for index, item in matches[self.offset:self.offset + self.limit]:
            record = {'index': index, 'value': _project_item(item, self.fields)}
            if len(encode(self._item_page(matches, source_count, page + [record])).encode()) > self.max_bytes:
                if not page:
                    raise _ItemTooLarge(f'Use fields projection, or raw view with the appropriate JSON pointer; item index {index}.')
                break
            page.append(record)
        return page


class Store:
    def __init__(self, root=None, quota=MAX_STORE, ttl=TTL):
        self.root = Path(root) if root else default_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.quota, self.ttl = quota, ttl
        self.db = sqlite3.connect(self.root / 'observations.sqlite3', timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS observations (
                ref TEXT PRIMARY KEY, scope TEXT, digest TEXT, body TEXT, size INTEGER, created REAL,
                UNIQUE(scope, digest));
            CREATE TABLE IF NOT EXISTS metrics (key TEXT PRIMARY KEY, value REAL);
        ''')

    def close(self):
        self.db.close()

    def metric(self, key, amount=1):
        self.db.execute('INSERT INTO metrics VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=value+excluded.value', (key, amount))

    def capture(self, value, scope='explicit', force=False):
        scope = session_scope.encode_scope(scope)
        start = time.monotonic()
        body = encode(value)
        size = len(body.encode())
        if size < THRESHOLD and not force:
            return {'kind': 'inline', 'value': value}
        if size > min(MAX_VALUE, self.quota):
            return error('CAPTURE_TOO_LARGE', 'Observation was not saved; project the value in JavaScript or narrow the source query.')
        digest = hashlib.sha256(body.encode()).hexdigest()
        now = time.time()
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute('DELETE FROM observations WHERE created < ?', (now - self.ttl,))
            existing = self.db.execute('SELECT ref FROM observations WHERE scope=? AND digest=?', (scope, digest)).fetchone()
            if existing:
                ref = existing[0]
            else:
                used = self.db.execute('SELECT COALESCE(SUM(size),0) FROM observations').fetchone()[0]
                while used + size > self.quota:
                    oldest = self.db.execute('SELECT ref,size FROM observations ORDER BY created LIMIT 1').fetchone()
                    self.db.execute('DELETE FROM observations WHERE ref=?', (oldest[0],))
                    used -= oldest[1]
                    self.metric('evictions')
                ref = 'ops://' + secrets.token_hex(24)
                self.db.execute('INSERT INTO observations VALUES (?,?,?,?,?,?)', (ref, scope, digest, body, size, now))
            result = {'kind': 'reference', 'ref': ref, 'storedBytes': size, 'sha256': digest,
                      'retentionSeconds': self.ttl, 'storedObservationComplete': True,
                      'metadata': metadata(value), 'preview': preview(value),
                      'retrieve': 'ops_result(ref, view="items"|"raw", path="", fields=[], query="", offset=0)'}
            self.metric('captures')
            self.metric('observationBytes', size)
            self.metric('previewBytes', len(encode(result).encode()))
            self.metric('captureMilliseconds', (time.monotonic() - start) * 1000)
        return result

    def get(self, ref):
        row = self.db.execute('SELECT body,created,scope FROM observations WHERE ref=?', (ref,)).fetchone()
        if not row or row[1] < time.time() - self.ttl:
            raise ReferenceUnavailable('Reference expired, was released, or was evicted; do not automatically repeat a mutating operation.')
        _require_owner(row[2])
        return json.loads(row[0])

    def result(self, ref, view='items', path='', fields=None, query='', offset=0, limit=40, max_bytes=6000, action='page'):
        try:
            if action == 'release':
                return self._release(ref)
            if action != 'page':
                raise ValueError('Use action page/release and view items/raw')
            page = _Page(ref, view, path, offset, limit, max_bytes, fields, query)
            result = page.render(self.get(ref))
            with self.db:
                self.metric('retrievals')
                self.metric('retrievalBytes', len(encode(result).encode()))
            return result
        except (ReferenceUnavailable, ValueError, KeyError, IndexError, TypeError) as exc:
            return _retrieval_error(exc)

    def _release(self, ref):
        with self.db:
            row = self.db.execute('SELECT scope FROM observations WHERE ref=?', (ref,)).fetchone()
            if row:
                _require_owner(row[0])
            removed = self.db.execute('DELETE FROM observations WHERE ref=?', (ref,)).rowcount
        return {'status': 'completed', 'released': bool(removed)}

    def stats(self):
        with self.db:
            self.db.execute('DELETE FROM observations WHERE created < ?', (time.time() - self.ttl,))
        count, size = self.db.execute('SELECT COUNT(*),COALESCE(SUM(size),0) FROM observations').fetchone()
        return {'liveReferences': count, 'liveBytes': size, 'quotaBytes': self.quota, 'ttlSeconds': self.ttl,
                'counters': dict(self.db.execute('SELECT key,value FROM metrics')),
                'measurement': 'UTF-8 observation/preview bytes, not tokens or realized model-context savings; nested hook previews may not be displayed.'}
