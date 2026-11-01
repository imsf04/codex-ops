"""Read-only installed-package smoke using the configured production interpreter."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
INSTALLED = Path.home() / '.codex/plugins/cache/personal/codex-ops/0.7.0'


def value(response):
    payload = response.structured_content or json.loads(response.content[0].text)
    return payload['value'] if payload.get('kind') == 'inline' else payload


async def main():
    config = json.loads((INSTALLED / '.mcp.json').read_text())['mcpServers']['codex_ops']
    with tempfile.TemporaryDirectory(prefix='codex-ops-installed-070-') as temporary:
        fixture = Path(temporary)
        (fixture / 'limits.py').write_text('KNOWN_LIMIT = 17\ndef cap(n):\n    return min(n, KNOWN_LIMIT)\n', encoding='utf-8')
        (fixture / 'build.log').write_text('INFO passed\n' * 5000 + 'ERROR INSTALL_070_SENTINEL\n', encoding='utf-8')
        inputs = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in fixture.iterdir()}
        env = {**config.get('env', {}), 'CODEX_OPS_STORE': str(fixture / 'cache'), 'CODEX_OPS_MEASUREMENT_ORIGIN': 'validation'}
        parameters = StdioServerParameters(command=config['command'], args=config['args'], env=env)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                catalogue = await session.list_tools()
                assert len(catalogue.tools) == 8
                assert all('ctx' not in tool.input_schema.get('properties', {}) for tool in catalogue.tools)
                async def workflow(operation, args):
                    return value(await session.call_tool('ops_workflow', {'root': str(fixture), 'operation': operation, 'args': args}))
                investigation = await workflow('investigate', {'question': 'Where is KNOWN_LIMIT used?'})
                assert investigation['kind'] == 'evidence-packet'
                assert 'return min' in json.dumps(investigation)
                diagnosis = await workflow('diagnose', {'logPath': 'build.log'})
                assert diagnosis['diagnostics'][0]['line'] == 5001
                saved = value(await session.call_tool('ops_capture', {'value': 'EVIDENCE_070_SENTINEL\n' * 700}))
                found = await workflow('evidence', {'refs': [saved['ref']], 'query': 'EVIDENCE_070_SENTINEL'})
                assert found['items'] and found['kind'] == 'evidence-packet'
                checkpoint = await workflow('working_set', {'action': 'save', 'sources': [{'ref': saved['ref']}]})
                recovered = await workflow('working_set', {'action': 'resume', 'workingSetRef': checkpoint['workingSetRef']})
                assert recovered['items'][0]['state'] == 'saved-observation'
                observations = [{'exit_code': 2, 'output': 'INFO routine passed\n' * 1000 + 'ERROR INSTALL_VERIFY_SENTINEL\n'}]
                verified = await workflow('verify', {'results': observations})
                assert verified['exitCode'] == 2 and 'INSTALL_VERIFY_SENTINEL' in json.dumps(verified['diagnosis'])
                reference = verified['observationsRef']
                text, offset, pages = '', 0, 0
                while True:
                    part = value(await session.call_tool('ops_result', {'ref': reference['ref'], 'view': 'raw', 'path': reference['path'], 'offset': offset, 'max_bytes': 16000}))
                    text += part['text']; pages += 1
                    offset = part['nextOffset']
                    if offset is None:
                        break
                assert json.loads(text) == observations
                stats = value(await session.call_tool('ops_stats', {'check_runtime': True}))
                assert stats['installation']['packageVersion'] == '0.7.0'
                assert stats['installation']['configuredVersion'] == '0.7.0'
                assert stats['installation']['stagedBundle']['valid']
        assert inputs == {name: hashlib.sha256((fixture / name).read_bytes()).hexdigest() for name in inputs}
        receipt = {'version': '0.7.0', 'passed': True, 'tools': 8, 'ctxHidden': True,
                   'investigate': True, 'logPathLine': 5001, 'evidence': True, 'workingSet': True,
                   'verifyObservedChunks': True, 'exactObservationRecoveryPages': pages,
                   'inputsUnchanged': True, 'productionInterpreter': config['command'],
                   'installation': stats['installation']}
        (ROOT / 'verification/installed-smoke-0.7.0.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print(json.dumps(receipt))


asyncio.run(main())
