"""Bounded diagnostic and record evidence; raw observations remain authoritative."""
import json
import re
from semantic_preview import source_text

ANSI = re.compile(r'\x1b\[[0-9;]*m')
DIAGNOSTIC = re.compile(r'(?:^\S+\(\d+,\d+\): error TS\d+:|^\S+:\d+:\d+ - error TS\d+:|'
    r'^error\[[A-Z]\d+\]:|^\s*E\s{3,}|'
    r'^FAILED\s+\S|^(?:FAIL|ERROR):|^Traceback \(most recent call last\):|'
    r'^[\w.]+(?:Error|Exception):|^\s*(?:error|warning):)', re.I)
LOCATION = re.compile(r'(?:[^\s:]+:\d+(?::\d+)?|[^\s]+\(\d+,\d+\)|File "[^"]+", line \d+)')
SUMMARY = re.compile(r'^(?:Ran \d+ tests? in |OK(?:\s|$)|FAILED \(|'
    r'=+.*\b\d+ (?:passed|failed|skipped)|Test Suites:|Tests:|'
    r'test result:|Found \d+ errors?|Build (?:succeeded|FAILED)|Time Elapsed)', re.I)
STATUS = re.compile(r'^(?:[ MADRCU?!]{2} .+|## .+)$')
ROW_FIELDS = ('id', 'name', 'title', 'path', 'url', 'status', 'error', 'message')


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())


def _short(value, limit=220):
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + ' …'
    return value if isinstance(value, (bool, int, float, type(None))) else _short(str(value), limit)


def _line(number, text):
    return {'line': number + 1, 'text': _short(text, 320)}


def _failure_indices(lines):
    return [index for index, line in enumerate(lines) if DIAGNOSTIC.search(line)]


def _kind(lines, failures):
    if lines and lines[0].startswith('diff --git '):
        return 'diff'
    if _status_lines(lines):
        return 'git-status'
    if failures:
        return 'diagnostic-evidence'
    return None


def _status_lines(lines):
    return bool(lines) and all(STATUS.fullmatch(line) for line in lines)


def _priority(lines, failures, kind):
    summaries = [i for i, line in enumerate(lines) if SUMMARY.search(line.strip())]
    if kind in ('diff', 'git-status'):
        changes = [i for i, line in enumerate(lines) if line.startswith(('diff ', '@@ ', '+', '-', '## '))]
        return list(dict.fromkeys(changes + list(range(len(lines)))))
    locations = _locations(lines)
    neighbors = _neighbors(len(lines), failures)
    return list(dict.fromkeys(summaries + failures + locations + neighbors))


def _locations(lines):
    return [i for i, line in enumerate(lines) if LOCATION.search(line)]


def _neighbors(count, failures):
    return [i for anchor in failures[:8] for i in range(max(0, anchor - 1), min(count, anchor + 3))]


def _select(lines, order, budget):
    selected = []
    for index in order:
        candidate = _line(index, lines[index])
        if _size(selected + [candidate]) > budget:
            continue
        selected.append(candidate)
    return sorted(selected, key=lambda row: row['line'])


def text_evidence(text, budget=1600):
    lines = [ANSI.sub('', line) for line in text.splitlines()]
    failures = _failure_indices(lines)
    kind = _kind(lines, failures)
    if kind is None:
        return None
    selected = _select(lines, _priority(lines, failures, kind), max(0, budget - 400))
    if not selected:
        return None
    shown = {row['line'] - 1 for row in selected}
    return {'kind': kind, 'lineCount': len(lines), 'evidence': selected,
        'diagnosticCount': len(failures), 'omittedDiagnostics': sum(i not in shown for i in failures),
        'omittedLines': len(lines) - len(selected), 'previewOnly': True,
        'sourceCompleteness': 'saved-observation-only'}


def preview(analysis, budget=1600):
    if analysis['kind'] != 'shell':
        return None
    if type(analysis['metadata'].get('exit_code')) is not int:
        return None
    text = analysis['value']['output']
    lines = text.splitlines()
    if _source_or_unknown(lines):
        return None
    return text_evidence(text, min(budget, max(300, len(text.encode()) // 2)))


def _source_or_unknown(lines):
    if _status_lines(lines):
        return False
    if source_text(lines):
        return True
    return not _supported_log(lines)


def _supported_log(lines):
    if lines and lines[0].startswith('diff --git '):
        return True
    return any(_log_marker(line) for line in lines)


def _log_marker(line):
    return bool(LOCATION.search(line) or SUMMARY.search(line.strip()) or line.startswith(
        ('Traceback (most recent call last):', 'FAILED ', 'error[')))


def _items(value):
    if isinstance(value, list):
        return value, ''
    if isinstance(value, dict) and isinstance(value.get('items'), list):
        return value['items'], '/items'
    return [], ''


def _record(row):
    return {key: _short(row[key]) for key in ROW_FIELDS if key in row}


def _failed(row):
    return bool(row.get('error')) or row.get('status') in ('error', 'failed', 'failure')


def records(value, budget):
    items, pointer = _items(value)
    if not _record_list(items):
        return None
    failed = [i for i, row in enumerate(items) if _failed(row)]
    order = list(dict.fromkeys(failed + list(range(min(len(items), 8)))))
    samples = _record_samples(items, order, budget)
    return {'kind': 'record-evidence', 'recordsPath': pointer, 'returnedItems': len(items),
        'failedItems': len(failed), 'sample': samples, 'omittedItems': len(items) - len(samples),
        'previewOnly': True, 'sourceCompleteness': 'saved-observation-only'}


def _record_list(items):
    return bool(items) and all(_interesting(row) for row in items)


def _interesting(row):
    return isinstance(row, dict) and bool(set(row).intersection(('name', 'title', 'status', 'error', 'message')))


def _record_samples(items, order, budget):
    samples = []
    for index in order:
        row = {'index': index, **_record(items[index])}
        if _size(samples + [row]) <= budget - 400:
            samples.append(row)
    return samples
