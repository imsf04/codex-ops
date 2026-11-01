"""Bounded discovery within an already saved observation; never rerun its producer."""
import re
from itertools import islice
from reducers import clip, encode

MAX_NODES = 10000
MAX_LINES = 20000
MAX_MATCHES = 2000
MAX_CHARACTERS = 1024 * 1024


def child_path(path, key):
    return path + '/' + str(key).replace('~', '~0').replace('/', '~1')


def describe(path, value):
    result = {'path': path, 'type': type(value).__name__}
    if isinstance(value, (dict, list, str)):
        result['size'] = len(value)
    if isinstance(value, str):
        result['sample'] = clip(value, 160)
    return result


def _outline_records(value, path, offset, limit):
    if isinstance(value, (dict, list)) and value:
        pairs, total = _children(value, path), len(value)
    else:
        pairs, total = iter(((path, value),)), 1
    return [describe(key, item) for key, item in islice(pairs, offset, offset + limit)], total


def _children(value, path):
    pairs = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else ()
    for key, item in pairs:
        yield child_path(path, key), item


def _walk(value, path):
    pending = [iter(((path, value),))]
    while pending:
        try:
            key, item = next(pending[-1])
        except StopIteration:
            pending.pop()
            continue
        yield key, item
        pending.append(_children(item, key))


def _lines(value):
    start = 0
    for match in re.finditer(r'\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]', value):
        yield value[start:match.start()]
        start = match.end()
    if start < len(value):
        yield value[start:]


class _Scan:
    def __init__(self, query):
        self.query, self.records, self.reason = query, [], None
        self.lines, self.characters = 0, 0

    def line(self, path, number, line):
        if self.lines >= MAX_LINES:
            self.reason = 'lines'
            return False
        self.lines += 1
        at = line.find(self.query)
        if at < 0:
            return True
        self.records.append({'path': path, 'line': number, 'text': clip(line[max(0, at - 80):], 300)})
        if len(self.records) >= MAX_MATCHES:
            self.reason = 'matches'
            return False
        return True

    def value(self, path, value):
        if not isinstance(value, str):
            return True
        selected = value[:MAX_CHARACTERS - self.characters]
        self.characters += len(selected)
        for number, line in enumerate(_lines(selected), 1):
            if not self.line(path, number, line):
                return False
        if len(selected) < len(value):
            self.reason = 'characters'
            return False
        return True


def find(value, path, query):
    scan = _scan(value, path, query)
    return scan.records, scan.reason is None


def _scan(value, path, query):
    if not query or len(query) > 200:
        raise ValueError('find requires a literal query of 1..200 characters')
    scan = _Scan(query)
    for visited, (key, item) in enumerate(_walk(value, path)):
        if visited >= MAX_NODES:
            scan.reason = 'nodes'
            break
        if not scan.value(key, item):
            break
    return scan


def _page_value(base, total, offset, result):
    end = offset + len(result)
    return {**base, 'items': result, 'matchedItems': total, 'pageComplete': end >= total,
            'complete': end >= total and base['scanComplete'],
            'nextOffset': end if end < total else None}


def page(records, offset, max_bytes, base, total):
    result = []
    for item in records:
        if len(encode(_page_value(base, total, offset, result + [item])).encode()) > max_bytes:
            break
        result.append(item)
    if not result and offset < total:
        raise ValueError('Increase max_bytes to retrieve this discovery item')
    return _page_value(base, total, offset, result)


def render(view, selected, path, query, offset, limit, max_bytes, base):
    if view == 'find':
        scan = _scan(selected, path, query)
        records, scanned = scan.records, scan.reason is None
        total = len(records)
        records = records[offset:offset + limit]
        base = {**base, 'scanLimits': {'nodes': MAX_NODES, 'lines': MAX_LINES, 'matches': MAX_MATCHES,
                                     'characters': MAX_CHARACTERS}, 'scanTruncatedBy': scan.reason}
        if not scanned:
            base['nextAction'] = 'Narrow path or query to inspect the unscanned remainder'
    else:
        records, total = _outline_records(selected, path, offset, limit)
        scanned = True
    base = {**base, 'scanComplete': scanned, 'sourceCompleteness': 'saved-observation-only'}
    return page(records, offset, max_bytes, base, total)
