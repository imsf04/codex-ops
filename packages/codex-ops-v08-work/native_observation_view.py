"""Derive bounded diagnostics from observed native chunks without executing anything."""
import re

DIAGNOSTIC = re.compile(r'\b(error|failed|failure|fatal|panic|exception|traceback|assertion|denied)\b|\w+Error:', re.I)
MAX_ROWS = 6
MAX_TEXT = 360


def _native(value):
    if not isinstance(value, dict) or not isinstance(value.get('output'), str):
        return False
    return bool({'exit_code', 'session_id', 'chunk_id'}.intersection(value))


def _state(value):
    code = value.get('exit_code')
    if type(code) is int:
        return 'completed' if code == 0 else 'failed'
    return 'running' if value.get('session_id') is not None else 'unknown'


def _row(index, text):
    return {'line': index + 1, 'text': text[:MAX_TEXT], 'clipped': len(text) > MAX_TEXT}


def _diagnostics(lines):
    matches = [(index, line) for index, line in enumerate(lines) if DIAGNOSTIC.search(line)]
    chosen = matches[-MAX_ROWS:]
    return [_row(index, line) for index, line in chosen], max(0, len(matches) - len(chosen))


def _tail(lines):
    start = max(0, len(lines) - 3)
    return [_row(index, lines[index]) for index in range(start, len(lines))]


def preview(analysis):
    value = analysis.get('value')
    if not _native(value):
        return None
    lines = value['output'].splitlines()
    diagnostics, omitted = _diagnostics(lines)
    state = _state(value)
    result = {'kind': 'native-observation', 'executionState': state,
              'exit_code': value.get('exit_code'), 'session_id': value.get('session_id'),
              'observedLines': len(lines), 'diagnostics': diagnostics,
              'omittedDiagnostics': omitted, 'tail': _tail(lines),
              'meaning': 'Observed chunk only; exit status and original value remain authoritative.'}
    if state == 'running':
        result['nextAction'] = 'Continue the existing native session; do not restart its command.'
    return result
