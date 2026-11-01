"""Read-only smoke against the native package's configured production Python/MCP."""
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

root = Path(__file__).resolve().parents[1]
installed = Path.home() / '.codex/plugins/cache/personal/codex-ops/0.6.1'
config = json.loads((installed / '.mcp.json').read_text())['mcpServers']['codex_ops']


def value(response):
    result = response.structured_content or json.loads(response.content[0].text)
    return result['value'] if result.get('kind') == 'inline' else result


async def main():
    with tempfile.TemporaryDirectory(prefix='codex-ops-installed-061-') as temporary:
        fixture = Path(temporary)
        (fixture / 'build.log').write_text('INFO passed\n' * 100 + 'ERROR INSTALLED_SENTINEL\n', encoding='utf-8')
        (fixture / 'notes.txt').write_text('small complete evidence\n', encoding='utf-8')
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in fixture.iterdir()}
        parameters = StdioServerParameters(command=config['command'], args=config['args'], env=config.get('env'))
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert len(tools.tools) == 8
                catalogue = value(await session.call_tool('ops_catalog', {'operation': 'workflows'}))
                assert 'javascript' not in catalogue and len(catalogue['recipes']) == 4
                diagnosis = value(await session.call_tool('ops_workflow', {'root': str(fixture),
                                  'operation': 'diagnose', 'args': {'logPath': 'build.log'}}))
                assert diagnosis['diagnostics'][0]['line'] == 101
                assert 'INSTALLED_SENTINEL' in diagnosis['diagnostics'][0]['text']
                documents = value(await session.call_tool('ops_workflow', {'root': str(fixture),
                    'operation': 'documents', 'args': {'requests': [{'operation': 'read',
                    'args': {'files': [{'path': 'notes.txt', 'offset': 1, 'limit': 10}]}}]}}))
                assert documents['items'][0]['result']['items'][0]['items'][0]['text'] == 'small complete evidence'
                assert 'resultRef' not in documents['items'][0]
                stats = value(await session.call_tool('ops_stats', {'check_runtime': True}))
                assert stats['installation']['packageVersion'] == '0.6.1'
                assert stats['installation']['configuredVersion'] == '0.6.1'
                assert stats['installation']['stagedBundle']['valid']
        assert hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in fixture.iterdir()}
        receipt = {'version': '0.6.1', 'tools': [t.name for t in tools.tools],
                   'lightweightCatalogue': True, 'logPathOriginalLine': 101,
                   'smallExactResultWithoutReference': True, 'sourceFilesUnchanged': True,
                   'productionPython': config['command'], 'installation': stats['installation']}
        (root / 'verification/installed-smoke-0.6.1.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print(json.dumps(receipt))


asyncio.run(main())
