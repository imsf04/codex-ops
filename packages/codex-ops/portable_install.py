"""Bind a prepared portable plugin to its extracted location."""
import json
import os
from pathlib import Path
import shlex
import sys


def configure(root, python):
    root = Path(root).resolve()
    python = Path(os.path.abspath(python))
    server = root / 'server.py'
    hook = root / 'hook.py'
    if not all(path.is_file() for path in (python, server, hook)):
        raise ValueError('The installed Python, server and hook must exist')
    descriptor = {'mcpServers': {'codex_ops': {
        'command': str(python), 'args': ['-u', str(server)],
        'env': {'PYTHONUTF8': '1'}, 'startup_timeout_sec': 30, 'tool_timeout_sec': 60,
    }}}
    if os.name == 'nt':
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        command = '& ' + quote(python) + ' ' + quote(hook)
    else:
        command = shlex.quote(str(python)) + ' ' + shlex.quote(str(hook))
        launcher = root / 'runtime_bridge/launcher_posix.py'
        if not launcher.is_file():
            raise ValueError('The POSIX bridge launcher is missing')
        entry = root / 'bin/codex-ops-cli'
        entry.write_text('#!/bin/sh\nexec ' + shlex.quote(str(python)) + ' ' +
                         shlex.quote(str(launcher)) + ' "$@"\n', encoding='utf-8')
        entry.chmod(0o755)
    hooks_path = root / 'hooks' / 'hooks.json'
    hooks = json.loads(hooks_path.read_text(encoding='utf-8'))
    for groups in hooks['hooks'].values():
        for group in groups:
            for item in group['hooks']:
                item['command'] = command
                if os.name == 'nt':
                    item['commandWindows'] = command
                else:
                    item.pop('commandWindows', None)
    (root / '.mcp.json').write_text(json.dumps(descriptor, indent=2) + '\n', encoding='utf-8')
    hooks_path.write_text(json.dumps(hooks, indent=2) + '\n', encoding='utf-8')
    return descriptor


if __name__ == '__main__':
    configure(Path(__file__).resolve().parent, sys.executable)
    print('Plugin configured for this directory. Register its local marketplace and trust its hooks.')
