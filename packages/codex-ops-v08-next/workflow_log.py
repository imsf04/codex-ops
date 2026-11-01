"""Select bounded log-file evidence through the existing native search adapter."""
import os

from workflow_validation import complete, require, text
from log_contract import COVERAGE

FAILURES = r'error|fail|exception|assert'
SUMMARIES = r'\bwarn(?:ing)?\b|passed|tests? ran|ran \d+ tests|test suites:'
CONTEXT = 3


def _search(root, path, pattern, maximum, invoke):
    return invoke(root, 'grep', {'path': path, 'pattern': pattern,
                                'caseInsensitive': True, 'lineNumbers': True,
                                'beforeContext': CONTEXT, 'afterContext': 0,
                                'outputMode': 'content', 'limit': maximum, 'exactTotal': True})


def _selection(root, path, maximum, invoke):
    preflight = invoke(root, 'stat', {'path': path})
    if preflight.get('status') == 'error':
        return preflight, 'failure'
    result = _search(root, path, FAILURES, maximum, invoke)
    if result.get('items') or not complete(result):
        return result, 'failure'
    return _search(root, path, SUMMARIES, maximum, invoke), 'warning-or-summary'


def _rows(result):
    rows = result.get('items', [])
    for row in rows:
        if not isinstance(row, dict) or type(row.get('line')) is not int:
            raise ValueError('Native log search returned invalid line evidence')
        if row['line'] < 1 or not isinstance(row.get('text'), str):
            raise ValueError('Native log search returned invalid line evidence')
    return rows


def _evidence(row):
    # Native grep reports the matched line and prefixes up to CONTEXT physical lines.
    lines = row['text'].split('\n')
    index = min(CONTEXT, row['line'] - 1)
    require(index < len(lines), 'Native log search omitted the matched line context')
    matched = lines[index]
    return {'line': row['line'], 'text': matched[:800], 'clipped': len(matched) > 800}


def _source(result, path, selection):
    source = {key: result[key] for key in COVERAGE if key in result}
    source.update({'path': path, 'selection': selection,
                   'coverageMeaning': 'Selected diagnostic matches; no total-log-line count is available.'})
    return source


def _lines(rows):
    return [line for row in rows for line in row['text'].split('\n')]


def _same_file(root, path, rows):
    expected = os.path.normcase(os.path.abspath(os.path.join(root, path)))
    for row in rows:
        actual = text(row.get('path'), 'native log evidence path', 32768)
        require(os.path.normcase(os.path.abspath(actual)) == expected,
                'Log path changed to a different source; inspect it before retrying')


def read(root, path, maximum, invoke):
    path = text(path, 'logPath', 4096)
    result, selection = _selection(root, path, maximum, invoke)
    if result.get('status') == 'error':
        return {'failure': result}
    rows = _rows(result)
    _same_file(root, path, rows)
    evidence = [_evidence(row) for row in rows]
    return {'lines': _lines(rows),
            'evidence': evidence, 'omitted': result.get('omitted', 0),
            'incomplete': not complete(result),
            'fields': {'logLinesScanned': None, 'logSource': _source(result, path, selection)}}
