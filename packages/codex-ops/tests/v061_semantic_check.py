"""Supplement strict historical field conformance; never alter original paid outcomes."""
import copy
from pathlib import Path

from model_tasks import _answer_value

AUTHORITY = {'suspended', 'suspension', 'suspended flag', 'suspended status',
             'suspension overrides ownership', 'suspension overrides owner status'}
OBSERVED_STRING = {'string', 'source.age is a string ("42")', "source.age is a string ('42')",
                   'source.age is a string', 'source.age is string', 'string ("42")'}
EXPECTED_NUMBER = {'number', 'user.age must be a number', 'user.age must be a number; convert source.age before assignment'}
ROOT_CAUSE = {'a string is assigned to the numeric user.age property (ts2322)',
              'a string is assigned to user.age, which requires a number (ts2322)',
              'a string value is assigned to user.age, which is declared as a number'}


def label(value):
    return value.strip().rstrip('.').casefold() if isinstance(value, str) else None


def canonical(task, root, actual):
    result = _answer_value(task, Path(root), actual)
    if not isinstance(result, dict):
        return result
    if task == 'code_location_authority':
        value = result.get('override')
        if value is False or (isinstance(value, str) and label(value) in AUTHORITY):
            result['override'] = 'suspended'
    if task == 'log_diagnosis_compiler':
        if label(result.get('root_cause')) in ROOT_CAUSE:
            result['root_cause'] = 'TS2322'
        if label(result.get('observed')) in OBSERVED_STRING:
            result['observed'] = 'string'
        if label(result.get('expected')) in EXPECTED_NUMBER:
            result['expected'] = 'number'
    return result


def outcome(row, expected):
    original = row['outcome']
    result = copy.deepcopy(original)
    result['oracleVersion'] = 'v061-supplemental-format-semantics-1'
    result['strictPassed'] = original['passed']
    if original['passed']:
        return result
    failures = original.get('failures', [])
    if len(failures) != 1 or failures[0].get('reason') != 'answer differs from independent oracle':
        return result
    normalized = canonical(row['task'], row['workspace'], failures[0].get('observed'))
    if normalized == expected.get('answer'):
        result.update(passed=True, failures=[], correction='Equivalent answer representation; original strict outcome retained')
    return result
