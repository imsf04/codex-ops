"""Apply loopback probe settings while retaining the initialized native sandbox home."""
import json
import os
from pathlib import Path
import tomllib

from run_model_benchmark import flags


def entries(value, prefix=''):
    for key, item in value.items():
        name = prefix + key
        if isinstance(item, dict):
            yield from entries(item, name + '.')
        else:
            yield name + '=' + json.dumps(item)


def apply(command, environment, config):
    settings = tomllib.loads(config)
    for server in settings.get('mcp_servers', {}).values():
        server['enabled'] = True
    additions = [arg for entry in entries(settings) for arg in ('-c', entry)]
    at = command.index('app-server')
    command[at:at] = flags() + additions
    environment['CODEX_HOME'] = os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))
    for name in ('CODEX_OPS_AUTO_OUTPUT', 'CODEX_OPS_BRIDGE_MANAGER_PID', 'CODEX_OPS_BRIDGE_SHIM_PID'):
        environment.pop(name, None)
