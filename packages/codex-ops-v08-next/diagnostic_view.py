"""Display log coordinates and scan/context boundaries without changing evidence."""
import document_view
from log_contract import COVERAGE

MAX_CONTEXT_LINES = 24


def _fields(value, names):
    return {name: value[name] for name in names if name in value}


def _log_source(diagnosis, view):
    source = diagnosis.get('logSource')
    if not isinstance(source, dict):
        return None
    names = (*COVERAGE, 'path', 'selection', 'coverageMeaning')
    view['logSource'] = _fields(source, names)
    return source.get('path')


def _coordinates(path):
    if isinstance(path, str) and path:
        return {'origin': 'log-file', 'path': path, 'lineBase': 1,
                'meaning': 'Physical line number in this log file; text is the diagnostic message.'}
    return {'origin': 'supplied-log-text', 'lineBase': 1,
            'meaning': 'Line number in supplied log text; original file or command-chunk offset is not established.'}


def _context(diagnosis, view):
    context = diagnosis.get('context')
    if not isinstance(context, dict):
        return
    fields = ('status', 'complete', 'failed', 'pending', 'truncated', 'nextIndex', 'total')
    summary = _fields(context, fields)
    failures = document_view.native_failures(context)
    if failures:
        summary.update(failures=failures[:4], omittedFailures=max(0, len(failures) - 4),
                       pathMeaning='Attempted source-context paths; failed reads are not verified source locations.')
    if summary:
        view['sourceContext'] = summary


def _line(row):
    if not isinstance(row, dict):
        return row
    number = row.get('line')
    if type(number) is not int or number < 1:
        return dict(row)
    result = dict(row)
    result['logLocation'] = {'line': result.pop('line')}
    result['kind'] = 'log-diagnostic'
    return result


def _readable(value):
    if not isinstance(value, dict) or value.get('error'):
        return False
    return value.get('status') in ('completed', 'partial') and isinstance(value.get('path'), str) and bool(value['path'])


def _source_rows(context):
    groups = []
    for file in context.get('items', []):
        if _readable(file):
            groups.append([_source_line(row, file) for row in file.get('items', []) if _valid_line(row, file)])
    return _interleave(groups)


def _interleave(groups):
    rows = []
    for index in range(max(map(len, groups), default=0)):
        rows.extend(group[index] for group in groups if index < len(group))
    return rows


def _valid_line(row, file):
    if not isinstance(row, dict) or row.get('path', file['path']) != file['path']:
        return False
    return type(row.get('line')) is int and row['line'] > 0 and isinstance(row.get('text'), str)


def _source_line(row, file):
    location = {'path': file['path'], 'line': row['line']}
    if isinstance(file.get('revision'), str) and file['revision']:
        location['revision'] = file['revision']
    return {'kind': 'source-context', 'sourceLocation': location, 'text': row['text'],
            **_fields(row, ('truncatedInLine',))}


def _context_rows(diagnosis, view):
    context = diagnosis.get('context')
    if not isinstance(context, dict):
        return []
    rows = _source_rows(context)
    if rows:
        view.setdefault('sourceContext', {}).update(omittedDisplayLines=max(0, len(rows) - MAX_CONTEXT_LINES))
    return rows[:MAX_CONTEXT_LINES]


def finish(view, candidates):
    if 'sourceContext' not in view:
        return
    selected = _source_count(candidates)
    if selected:
        summary = view['sourceContext']
        summary['shownLines'] = _source_count(view['evidence'])
        summary['omittedDisplayLines'] += selected - summary['shownLines']


def _source_count(rows):
    return sum(isinstance(row, dict) and row.get('kind') == 'source-context' for row in rows)


def rows(diagnosis, view):
    if 'diagnostics' not in diagnosis:
        return []
    path = _log_source(diagnosis, view)
    view['diagnosticCoordinates'] = _coordinates(path)
    view.update(_fields(diagnosis, ('logLinesScanned', 'omittedDiagnostics',
                                   'omittedLocations', 'outsideRootLocations')))
    _context(diagnosis, view)
    return [_line(row) for row in diagnosis.get('diagnostics', [])] + _context_rows(diagnosis, view)
