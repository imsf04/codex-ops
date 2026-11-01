"""Call the installed native package's configured production MCP entrypoint."""
import asyncio
import json
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

root = Path(__file__).resolve().parents[1]
installed = Path.home() / '.codex/plugins/cache/personal/codex-ops/0.6.0'
config = json.loads((installed / '.mcp.json').read_text())['mcpServers']['codex_ops']

async def main():
    params = StdioServerParameters(command=config['command'], args=config['args'], env=config.get('env'))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            assert len(listed.tools) == 8
            catalog = await session.call_tool('ops_catalog', {'operation': 'task'})
            data = catalog.structured_content or json.loads(catalog.content[0].text)
            assert len(data['operationSchemas']) == 11
            sdk = await session.call_tool('ops_workflow', {'root': str(root), 'operation': 'sdk', 'args': {}})
            value = sdk.structured_content or json.loads(sdk.content[0].text)
            assert value['kind'] == 'inline' and 'runAndDiagnose' in value['value']['javascript']
            stats = await session.call_tool('ops_stats', {'check_runtime': True})
            snapshot = stats.structured_content or json.loads(stats.content[0].text)
            assert snapshot['installation']['packageVersion'] == '0.6.0'
            assert snapshot['installation']['stagedBundle']['valid']
            receipt = {'tools': [tool.name for tool in listed.tools], 'taskOperationSchemas': 11,
                'sdkCallableFactory': True, 'productionPython': config['command'],
                'installation': snapshot['installation'], 'nativePackage': str(installed)}
            (root / 'verification/installed-smoke-0.6.0.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
            print(json.dumps({'tools': len(listed.tools), 'sdk': True, 'bundleValid': True}))

asyncio.run(main())
