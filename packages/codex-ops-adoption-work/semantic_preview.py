"""Recognize completed test/build transcripts without interpreting source prose as logs."""
import json
import re

DIAGNOSTIC = re.compile(r'^\s*(?:(?:\[[^\]\n]{1,50}\]|\d{4}-\d\d-\d\dT\S+)\s+)?(?:'
    r'(?:ERROR|WARN(?:ING)?|FAIL(?:ED|URE)?|PANIC)(?::|\s+\d|\s{2,})|'
    r'Traceback \(most recent call last\):|[A-Za-z_][\w.]*Error:|'
    r'E\s{3,}|FAIL:|ERROR:|FAILED \(|test result: FAILED)', re.I)
TEST_SUMMARY = re.compile(r'^(?:Ran \d+ tests? in |={2,}.*\b\d+ (?:passed|failed|skipped)|'
                          r'Test Suites:|Tests:|test result: (?:ok|FAILED)\.)')
TEST_SUCCESS = re.compile(r'^(?:OK(?: \([^\n]*\))?|FAILED \([^\n]*\)|={2,}.*\b\d+ (?:passed|failed|skipped).*)$')
PASS_LINE = re.compile(r'^(?:test\w* \([^\n]+\) \.\.\. ok|'
                       r'test [^\n]+ \.\.\. (?:ok|ignored)|'
                       r'(?:tests?[/\\][^\s]+|[^\s]+_test\.[^\s]+) [\.s]+\s+\[\s*\d+%\]|'
                       r'PASS\s+\S+\.(?:[cm]?[jt]sx?)(?: \([^\n]+\))?|[.s]+)$')
BUILD_SUMMARY = re.compile(r'^\s*(?:Build succeeded\.|Finished `[^`]+` profile \[.*\] target\(s\) in )')
BUILD_PROGRESS = re.compile(r'^\s*(?:Compiling|Checking) [\w.-]+ v[\w.+-]+(?: \([^\n]*\))?\s*$')
WARNING = re.compile(r'^\s*(?:(?:\[[^\]\n]{1,50}\]|\d{4}-\d\d-\d\dT\S+)\s+)?WARN(?:ING)?(?::|\s)', re.I)
COLOR = re.compile(r'\x1b\[[0-9;]*m')


def source_text(lines):
    first = next((line.lstrip() for line in lines if line.strip()), '')
    return first.startswith(('# ', '## ', '#!', '```', '"""', "'''", 'import ', 'from ',
                             'def ', 'class ', 'const ', 'let ', 'function ', 'export ',
                             'package ', 'use ', 'fn ', '//', '/*'))


def diagnostic(line):
    return bool(DIAGNOSTIC.search(line))


def failure(line):
    return diagnostic(line) and not WARNING.search(line)


def _test_log(lines):
    summaries = [line.strip() for line in lines if TEST_SUMMARY.search(line.strip())]
    return bool(summaries) and _test_completion(lines, summaries)


def _test_completion(lines, summaries):
    return any(TEST_SUCCESS.fullmatch(line.strip()) for line in lines) or any(
        line.startswith(('Test Suites:', 'test result:')) for line in summaries)


def _kind(lines):
    if source_text(lines):
        return None
    if _test_log(lines):
        return 'test-summary'
    if any(BUILD_SUMMARY.search(line) for line in lines):
        return 'build-summary'
    return None


def _routine(line, kind):
    if not line.strip():
        return True
    if kind == 'test-summary':
        return bool(PASS_LINE.fullmatch(line.strip()) or re.fullmatch(r'[-=]{4,}', line.strip()))
    return bool(BUILD_PROGRESS.fullmatch(line))


def _select(lines, kind):
    kept, omitted = [], 0
    for number, line in enumerate(lines, 1):
        if _routine(line, kind) and not diagnostic(line):
            omitted += 1
        else:
            kept.append({'line': number, 'text': line})
    return kept, omitted


def preview(analysis):
    if analysis['kind'] != 'shell':
        return None
    value, state = analysis['value'], analysis['metadata']
    if type(state.get('exit_code')) is not int:
        return None
    lines = [COLOR.sub('', line) for line in value['output'].splitlines()]
    kind = _kind(lines)
    return _summary(lines, kind) if kind is not None else None


def _summary(lines, kind):
    kept, omitted = _select(lines, kind)
    if omitted < 3:
        return None
    result = {'kind': kind, 'lineCount': len(lines), 'omittedRoutineLines': omitted,
              'previewOnly': True, 'evidence': kept}
    return result if len(json.dumps(result, ensure_ascii=False).encode()) <= 1600 else None
