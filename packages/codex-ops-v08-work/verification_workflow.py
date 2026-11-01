"""Diagnose observed native execution chunks; this module never runs commands."""
from workflow_validation import options, require


def _observations(args):
    options(args, ('results', 'maxEvidence', 'maxLocations', 'before', 'after'))
    values = args.get('results')
    require(isinstance(values, list) and 1 <= len(values) <= 9, 'results must contain 1..9 native observations')
    for value in values:
        require(isinstance(value, dict), 'Native observation must be an object')
        require(isinstance(value.get('output', ''), str), 'Native output must be text')
    return values


def _state(shell):
    if type(shell.get('exit_code')) is int:
        return 'completed'
    if shell.get('session_id') is not None:
        return 'running'
    return 'unknown'


def _diagnosis(root, args, values, invoke):
    final = values[-1]
    if not _failed(final):
        return None, None
    output = ''.join(value.get('output', '') for value in values)
    if len(output.encode('utf-8')) > 262144:
        return None, 'Observed output exceeds 256 KiB; select bounded evidence explicitly'
    limits = _limits(args)
    return invoke(root, 'diagnose', dict(limits, log=output)), None


def _failed(shell):
    return _state(shell) == 'completed' and shell['exit_code'] != 0


def _limits(args):
    return {key: value for key, value in args.items() if key != 'results'}


def run(root, args, invoke):
    values = _observations(args)
    diagnosis, skipped = _diagnosis(root, args, values, invoke)
    final = values[-1]
    return {'status': 'completed', 'effectState': 'none', 'operation': 'verify',
            'executionState': _state(final), 'exitCode': final.get('exit_code'),
            'sessionId': final.get('session_id'), 'observations': values,
            'diagnosis': diagnosis, 'diagnosticSkipped': skipped,
            'coverage': {'observations': len(values), 'sourceComplete': False,
                         'meaning': 'Caller-provided native observations only; not proof of entire process output'},
            'nextAction': _next(final)}


def _next(shell):
    if _state(shell) == 'running':
        return {'tool': 'write_stdin', 'args': {'session_id': shell['session_id'], 'chars': ''}}
    if _state(shell) == 'unknown':
        return 'Inspect native execution diagnostics; do not rerun a command to recover unknown effects'
    return 'Inspect the native exit code and diagnostic evidence'
