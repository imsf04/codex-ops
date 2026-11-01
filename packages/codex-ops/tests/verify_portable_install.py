"""Exercise an installed plugin's configured MCP server and SessionStart hook."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def verify(plugin, root, env):
    spec = json.loads((plugin / '.mcp.json').read_text(encoding='utf-8'))['mcpServers']['codex_ops']
    params = StdioServerParameters(command=spec['command'], args=spec['args'], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert 'ops_files' in [tool.name for tool in tools.tools]
            result = await session.call_tool('ops_files', {
                'root': str(root), 'operation': 'read', 'args': {'files': [{'path': 'sample.txt'}]}})
            assert not result.is_error and 'installed plugin evidence' in str(result), result
    hooks = json.loads((plugin / 'hooks/hooks.json').read_text(encoding='utf-8'))
    command = hooks['hooks']['SessionStart'][0]['hooks'][0]['command']
    shell = ['powershell', '-NoProfile', '-Command', command] if os.name == 'nt' else ['sh', '-c', command]
    process = subprocess.run(shell, input=json.dumps({'hook_event_name': 'SessionStart'}),
                             text=True, capture_output=True, env=env, check=True)
    assert 'hookSpecificOutput' in json.loads(process.stdout), process.stdout


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='codex-ops-install-test-') as temporary:
        root = Path(temporary).resolve()
        (root / 'sample.txt').write_text('installed plugin evidence\n', encoding='utf-8')
        env = {key: value for key, value in os.environ.items() if key not in ('CODEX_OPS_WORKER', 'CODEX_OPS_KERNEL')}
        env.update({'CODEX_OPS_STORE': str(root / 'store'), 'PYTHONUTF8': '1'})
        asyncio.run(verify(Path(sys.argv[1]).resolve(), root, env))
    print('Installed plugin MCP and SessionStart hook passed')
