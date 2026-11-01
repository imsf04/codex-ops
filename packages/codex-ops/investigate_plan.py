"""Bounded task-intent search plans; lexical clues never imply semantic certainty."""
from pathlib import Path
import re

EXCLUDED = ['!**/verification/**', '!**/coverage/**', '!**/dist/**', '!**/build/**',
            '!**/*.min.js', '!**/*.map', '!**/package-lock.json', '!**/uv.lock', '!**/Cargo.lock']
TESTS = ['**/test*/**', '**/*test*', '**/*spec*']
CONFIG = ['**/*config*', '**/*settings*', '**/*.toml', '**/*.yaml', '**/*.yml', '**/*.ini', '**/*.env.example']
TEST_WORDS = re.compile(r'\b(test|tests|testing|tested|regression|spec|specs)\b|测试|回归|用例', re.I)
CONFIG_WORDS = re.compile(r'\b(config|configuration|configured|settings)\b|配置', re.I)


def _primary(focus):
    return 'source' if focus == 'auto' else focus


def _requested(query):
    return [(query['focus'] == 'failure' or TEST_WORDS.search(query['question']), 'tests'),
            (CONFIG_WORDS.search(query['question']), 'configuration')]


def _roles(query):
    requested = [role for included, role in _requested(query) if included]
    return list(dict.fromkeys([_primary(query['focus']), *requested]))


def _pattern(query, role):
    literal = '|'.join(re.escape(item) for item in query['anchors'])
    if role == 'definition':
        return rf'(?:\b(?:def|fn|function|class|struct|enum|const|let|var|type|interface)\s+(?:{literal})\b|(?:{literal})\s*(?::[^=]{{0,80}})?=)'
    return literal


def _globs(role):
    patterns = {'tests': TESTS, 'configuration': CONFIG}.get(role, ['**'])
    return patterns + EXCLUDED


def _bounds(role):
    if role == 'references':
        return 2, 4, 24, 6
    if role in ('definition', 'failure'):
        return 8, 16, 16, 4
    return 4, 10, 16, 4


def _stage(query, path, role):
    before, after, matches, files = _bounds(role)
    return {'role': role, 'path': path, 'pattern': _pattern(query, role), 'glob': _globs(role),
            'before': before, 'after': after, 'maxMatches': matches, 'maxFiles': files}


def _path_roles(root, path, roles):
    if (Path(root) / path).is_file():
        return roles[:1]
    return roles


def build(root, query):
    roles = _roles(query)
    return {'plans': [_stage(query, path, role) for path in query['paths']
                      for role in _path_roles(root, path, roles)]}
