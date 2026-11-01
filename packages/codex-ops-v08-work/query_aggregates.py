"""Bounded declarative counts over saved observations; no producer re-execution."""
import io
import json
from reducers import encode
from retrieval_views import page

MAX_RECORDS = 100000
MAX_GROUPS = 1000


def _records(value):
    if isinstance(value, list):
        return iter(value)
    if isinstance(value, str):
        return (line.rstrip('\r\n') for line in io.StringIO(value, newline=None))
    return iter((value,))


def _field(view, fields):
    if view == 'count':
        if fields:
            raise ValueError('count uses path/query; fields is reserved for group')
        return None
    if fields in (None, []):
        return None
    if len(fields) != 1 or not isinstance(fields[0], str):
        raise ValueError('group fields must name exactly one top-level scalar field')
    return fields[0]


def _key(item, field):
    if field is not None:
        if not isinstance(item, dict) or field not in item:
            return None
        item = item[field]
    if isinstance(item, (dict, list)):
        raise ValueError('group requires scalar values; select a scalar field')
    key = encode(item)
    if len(key.encode()) > 1024:
        raise ValueError('Group key exceeds 1024 bytes; narrow path or select a shorter field')
    return key


class _Scan:
    def __init__(self, view, field, query):
        self.view, self.field, self.query = view, field, query
        self.processed = self.matched = self.missing = 0
        self.groups = {}
        self.reason = None

    def accept(self, item):
        if self.query and self.query not in (item if isinstance(item, str) else encode(item)):
            self.processed += 1
            return True
        if self.view == 'group' and not self.group(item):
            return False
        self.processed += 1
        self.matched += 1
        return True

    def group(self, item):
        key = _key(item, self.field)
        if key is None:
            self.missing += 1
            return True
        if key not in self.groups and len(self.groups) >= MAX_GROUPS:
            self.reason = 'groups'
            return False
        self.groups[key] = self.groups.get(key, 0) + 1
        return True

    def run(self, selected):
        for index, item in enumerate(_records(selected)):
            if index >= MAX_RECORDS:
                self.reason = 'records'
                break
            if not self.accept(item):
                break
        return self

    def rows(self):
        if self.view == 'count':
            return [{'count': self.matched}]
        return [{'key': json.loads(key), 'count': self.groups[key]} for key in sorted(self.groups)]


def render(view, selected, fields, query, offset, limit, max_bytes, base):
    if len(query) > 200:
        raise ValueError('Aggregate literal query is limited to 200 characters')
    scan = _Scan(view, _field(view, fields), query).run(selected)
    rows = scan.rows()
    base = {**base, 'processedItems': scan.processed, 'matchedRecords': scan.matched,
            'missingFieldItems': scan.missing, 'scanComplete': scan.reason is None,
            'scanTruncatedBy': scan.reason, 'scanLimitRecords': MAX_RECORDS,
            'sourceCompleteness': 'saved-observation-only'}
    return page(rows[offset:offset + limit], offset, max_bytes, base, len(rows))
