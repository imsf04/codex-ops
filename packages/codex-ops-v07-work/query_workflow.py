"""Bounded search and context reads through the existing native file adapter."""
import time

from store import error

BOUNDS = {'offset': (0, 1000000, 0), 'maxMatches': (1, 64, 20),
          'maxFiles': (1, 8, 4), 'before': (0, 20, 3), 'after': (0, 20, 3)}
KEYS = frozenset((*BOUNDS, 'path', 'pattern', 'glob', 'caseInsensitive'))
MAX_RANGES = 32
TOTAL_SECONDS = 45
PHASE_SECONDS = 22


def _text(value, label, maximum):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise ValueError(f'{label} must be a nonempty string of at most {maximum} characters')
    return value


def _number(args, key):
    low, high, default = BOUNDS[key]
    value = args.get(key, default)
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{key} must be an integer in {low}..{high}')
    return value


def _glob(value):
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError('glob must be an array of at most 32 strings')
    return [_text(item, 'glob entry', 512) for item in value]


def options(args):
    if not isinstance(args, dict) or set(args) - KEYS:
        raise ValueError('search accepts path, pattern, glob, caseInsensitive, offset, maxMatches, maxFiles, before and after')
    result = {key: _number(args, key) for key in BOUNDS}
    result.update(path=_text(args.get('path', '.'), 'path', 4096),
                  pattern=_text(args.get('pattern'), 'pattern', 4096), glob=_glob(args.get('glob', [])))
    result['caseInsensitive'] = args.get('caseInsensitive', False)
    if type(result['caseInsensitive']) is not bool:
        raise ValueError('caseInsensitive must be a boolean')
    return result


def _grep(options):
    return {'path': options['path'], 'pattern': options['pattern'], 'glob': options['glob'],
            'caseInsensitive': options['caseInsensitive'], 'offset': options['offset'],
            'limit': options['maxMatches'], 'outputMode': 'content', 'lineNumbers': True,
            'beforeContext': 0, 'afterContext': 0, 'exactTotal': False}


def _valid_match(row):
    if not isinstance(row, dict):
        return False
    return isinstance(row.get('path'), str) and type(row.get('line')) is int and row['line'] >= 1 and isinstance(row.get('text'), str)


def _select(matches, maximum):
    selected, paths = [], set()
    for index, row in enumerate(matches):
        if row['path'] not in paths and len(paths) >= maximum:
            continue
        paths.add(row['path'])
        selected.append((index, row))
    return selected


def _merge(ranges, start, end):
    if ranges and start <= ranges[-1][1] + 1:
        ranges[-1][1] = max(end, ranges[-1][1])
    else:
        ranges.append([start, end])


def _ranges(selected, before, after):
    grouped = {}
    for _, row in selected:
        grouped.setdefault(row['path'], []).append(row['line'])
    requested = []
    for path, lines in grouped.items():
        ranges = []
        for line in sorted(lines):
            _merge(ranges, max(1, line - before), line + after)
        requested.extend({'path': path, 'offset': start, 'limit': end - start + 1} for start, end in ranges)
    return requested


def _covered(row, requests):
    return any(request['path'] == row['path'] and request['offset'] <= row['line'] < request['offset'] + request['limit']
               for request in requests)


def _lines(read):
    result = {}
    for item in read.get('items', []):
        for row in item.get('items', []):
            result[(row.get('path', item.get('path')), row.get('line'))] = row.get('text')
    return result


def _check(row, lines):
    key = row['path'], row['line']
    if key not in lines:
        return 'unavailable'
    return 'unchanged' if lines[key] == row['text'] else 'changed'


def _checks(selected, lines):
    return [{'matchIndex': index, 'path': row['path'], 'line': row['line'],
             'state': _check(row, lines)} for index, row in selected]


def _failed(read):
    return read.get('status') in ('error', 'rejected') or any(read.get(key) for key in ('failed', 'pending', 'truncated'))


def _partial(search, omitted, read, checks):
    incomplete = not search.get('scanComplete', False) or omitted > 0 or _failed(read)
    return incomplete or any(row['state'] != 'unchanged' for row in checks)


def _result(search, selected, requested, read, total_ranges):
    matches = search['items']
    checks = _checks(selected, _lines(read))
    omitted = len(matches) - len(selected)
    partial = _partial(search, omitted, read, checks)
    facts = {key: value for key, value in search.items() if key != 'items'}
    return {'status': 'partial' if partial else 'completed', 'effectState': 'none',
            'sourceCompleteness': 'per-stage', 'snapshotConsistency': 'non-atomic; matched lines compared only',
            'search': facts, 'matches': matches, 'selectedMatches': len(selected), 'omittedMatches': omitted,
            'requestedRanges': requested, 'omittedRanges': total_ranges - len(requested),
            'context': read, 'matchChecks': checks,
            'nextAction': 'Use search.nextOffset for another search page; narrow path or raise bounds for omitted context'}


def _call(invoke, operation, args, deadline, clock):
    remaining = min(PHASE_SECONDS, deadline - clock())
    if remaining < 2:
        return error('WORKFLOW_TIMEOUT', 'Search/context deadline reached; narrow the query')
    return invoke(operation, args, remaining)


def _search(options, invoke, clock):
    deadline = clock() + TOTAL_SECONDS
    search = _call(invoke, 'grep', _grep(options), deadline, clock)
    if search.get('status') in ('error', 'rejected'):
        return search
    matches = search.get('items')
    if not isinstance(matches, list) or not all(_valid_match(row) for row in matches):
        return error('SEARCH_SHAPE', 'Native search returned unsupported match records')
    return _contexts(options, search, invoke, deadline, clock)


def _contexts(options, search, invoke, deadline, clock):
    selected = _select(search['items'], options['maxFiles'])
    ranges = _ranges(selected, options['before'], options['after'])
    requested = ranges[:MAX_RANGES]
    selected = [(index, row) for index, row in selected if _covered(row, requested)]
    read = {'status': 'completed', 'items': [], 'pending': 0}
    if requested:
        read = _call(invoke, 'read', {'files': requested}, deadline, clock)
    return _result(search, selected, requested, read, len(ranges))


def run(root, args, invoke, clock=time.monotonic):
    """invoke(operation,args,seconds) must retain the selected root's native path checks."""
    try:
        return _search(options(args), invoke, clock)
    except (ValueError, TypeError, KeyError) as exc:
        return error('INVALID_ARGUMENT', str(exc))
