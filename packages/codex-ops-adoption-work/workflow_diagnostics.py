"""Extract bounded failure evidence and read source context without running commands."""
import re
from pathlib import Path
from structured import analyze
import workflow_log

from workflow_validation import callback, integer, options, require, text

PATTERNS = (
    re.compile(r'File "([^"\n]+)", line (\d+)'),
    re.compile(r'^\s*((?:[A-Za-z]:)?[^\n"{}]*?\.[A-Za-z0-9]+):(\d+)(?::\d+)?'),
    re.compile(r'^\s*([^\n"{}]+?\.[A-Za-z0-9]+)\((\d+),\d+\)\s*:\s*(?:error|warning)'),
)
DIAGNOSTIC = re.compile(r'error|fail|\bwarn(?:ing)?\b|exception|assert|passed|tests? ran|ran \d+ tests|test suites:', re.I)
FAILURE = re.compile(r'error|fail|exception|assert', re.I)
WARNING = re.compile(r'warn', re.I)
ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
MAX_LOG_BYTES = 262144


def _log(args, load):
    require(('log' in args) != ('logRef' in args), 'Provide exactly one of log or logRef')
    if 'log' in args:
        return _log_text(text(args['log'], 'log', MAX_LOG_BYTES, empty=True))
    ref = text(args['logRef'], 'logRef', 256)
    value = callback(load, 'load')(ref)
    return _log_text(value)


def _log_text(value):
    wrapped = _fulfilled_shell(value)
    if wrapped is not None:
        return text(wrapped['output'], 'fulfilled shell output', MAX_LOG_BYTES, empty=True)
    if isinstance(value, dict):
        return text(value.get('output'), 'saved shell output', MAX_LOG_BYTES, empty=True)
    value = text(value, 'saved log text or shell output', MAX_LOG_BYTES, empty=True)
    shell = _decoded_shell(analyze(value))
    if shell is not None:
        return text(shell['output'], 'decoded shell output', MAX_LOG_BYTES, empty=True)
    return value


def _fulfilled_shell(value):
    if not isinstance(value, dict):
        return None
    if set(value) != {'status', 'value'} or value['status'] != 'fulfilled':
        return None
    decoded = analyze(value['value'])
    return decoded['value'] if decoded['kind'] == 'shell' else None


def _decoded_shell(decoded):
    if decoded['kind'] == 'shell':
        return decoded['value']
    return _fulfilled_shell(decoded['value'])


def _match(line):
    line = _source_line(line)
    for pattern in PATTERNS:
        found = pattern.search(line)
        if found:
            return found.group(1).strip(), int(found.group(2))
    return None


def _source_line(line):
    line = ANSI.sub('', line).strip()
    if line.startswith('--> '):
        return line[4:]
    if line.startswith('at '):
        return line.rsplit('(', 1)[-1].removesuffix(')') if '(' in line else line[3:]
    return line


def _location(root, found):
    if found is None:
        return None
    name, line = found
    path = Path(name)
    path = path if path.is_absolute() else Path(root) / path
    if line < 1 or not path.resolve().is_relative_to(Path(root)):
        return None
    return str(path), line


def _locations(root, lines):
    result, seen, rejected = [], set(), 0
    for line in lines:
        found = _match(line)
        location = _location(root, found)
        rejected += int(found is not None and location is None)
        if location is not None and location not in seen:
            result.append(location)
            seen.add(location)
    return result, rejected


def _priority(line):
    if FAILURE.search(line):
        return 0
    return 1 if WARNING.search(line) else 2


def _evidence(lines, maximum):
    selected = [{'line': index + 1, 'text': line[:800], 'clipped': len(line) > 800}
                for index, line in enumerate(lines) if DIAGNOSTIC.search(line)]
    selected.sort(key=lambda item: (_priority(lines[item['line'] - 1]), item['line']))
    evidence = sorted(selected[:maximum], key=lambda item: item['line'])
    return evidence, max(0, len(selected) - maximum)


def _observation(root, args, maximum, invoke, load):
    selected = sum(key in args for key in ('log', 'logRef', 'logPath'))
    require(selected == 1, 'Provide exactly one of log, logRef or logPath')
    if 'logPath' in args:
        return workflow_log.read(root, args['logPath'], maximum, invoke)
    lines = _log(args, load).splitlines()
    evidence, omitted = _evidence(lines, maximum)
    return {'lines': lines, 'evidence': evidence, 'omitted': omitted,
            'incomplete': False, 'fields': {'logLinesScanned': len(lines)}}


def _status(observation, locations):
    if observation['incomplete'] or observation['omitted']:
        return 'partial'
    return 'partial' if locations else 'completed'


def run(root, args, invoke, load):
    options(args, ('log', 'logRef', 'logPath', 'maxLocations', 'maxEvidence', 'before', 'after'))
    maximum = integer(args, 'maxLocations', 1, 16, 6)
    evidence_limit = integer(args, 'maxEvidence', 1, 40, 12)
    before = integer(args, 'before', 0, 20, 3)
    after = integer(args, 'after', 0, 20, 3)
    observation = _observation(root, args, evidence_limit, invoke, load)
    if 'failure' in observation:
        return observation['failure']
    locations, rejected = _locations(root, observation['lines'])
    requests = [{'path': path, 'offset': max(1, line - before),
                 'limit': line + after - max(1, line - before) + 1} for path, line in locations[:maximum]]
    context = invoke(root, 'read', {'files': requests}) if requests else {'status': 'completed', 'items': []}
    return {'status': _status(observation, locations),
            'effectState': 'none', 'operation': 'diagnose', **observation['fields'],
            'diagnostics': observation['evidence'], 'omittedDiagnostics': observation['omitted'], 'sourceRequests': requests,
            'omittedLocations': max(0, len(locations) - maximum), 'outsideRootLocations': rejected,
            'context': context, 'sourceCompleteness': 'Selected diagnostic evidence and source ranges; inspect coverage and omissions.',
            'nextAction': 'Inspect diagnostics, context and logSource coverage; retrieve the original log or explicit file ranges for omitted evidence. No command was run.'}
