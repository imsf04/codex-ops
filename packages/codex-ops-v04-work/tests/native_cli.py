"""Resolve the unwrapped CLI when Desktop puts the custom shim on PATH."""
import os
from pathlib import Path
import shutil
import json


def mcp_python():
    manifest = Path(__file__).resolve().parents[1] / '.mcp.json'
    return Path(json.loads(manifest.read_text(encoding='utf-8'))['mcpServers']['codex_ops']['command'])


def native_cli():
    selected = shutil.which('codex') or os.environ.get('CODEX_APP_RUNTIME_CLI_PATH')
    if not selected:
        raise RuntimeError('Native CLI or Desktop runtime selector is required')
    executable = Path(selected)
    adjacent = executable.parent / 'real-cli.txt'
    if adjacent.is_file():
        executable = Path(adjacent.read_text(encoding='utf-8').strip())
    return str(executable)
