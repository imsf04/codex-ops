"""Read-only staged planning and argv discovery for native permissioned execution."""
from pathlib import Path
import re
import sys
from mutations.paths import require, root_path
from mutations.task_planning import plan


def summary(value):
    return {'status': 'planned', 'effectState': 'none', 'root': value['root'],
            'planDigest': value['planDigest'], 'stageCount': len(value['stages']),
            'stepCount': len(value['steps']), 'roots': value['roots'],
            'steps': [{'operation': step['operation'], 'path': step['args']['path'],
                       'stage': step['stage']} for step in value['steps']],
            'bounds': {'nodes': 128, 'totalBytes': 8 * 1024 * 1024, 'fileBytes': 1024 * 1024},
            'execution': 'Native shell only; current Codex permissions apply. Plan grants no authority.'}


def command(action, root='', identity='', reference=''):
    require(action in ('apply', 'status', 'resume', 'rollback', 'cancel'), 'Unknown task action')
    argv = [str(Path(__file__).resolve().parent / 'mutations/task_cli.py'), action]
    if action == 'apply':
        require(bool(re.fullmatch(r'ops://[a-f0-9]{48}', reference)), 'Expected a saved task plan reference')
        argv += ['--plan-ref', reference]
    else:
        require(isinstance(identity, str) and bool(re.fullmatch('[a-f0-9]{32}', identity)), 'Expected a task ID')
        argv += ['--root', str(root_path(root)), '--id', identity]
    return {'executable': sys.executable, 'args': argv,
            'requiresNativePermission': True, 'executionComplete': False,
            'cancellation': 'Cooperative before next task step; use native process control for an active shell.'}
