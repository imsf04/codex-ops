import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


class NativePlanMcpTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovered_planner_executes_only_after_native_cli_call_and_can_rollback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'a.txt').write_text('before')
            env = {**os.environ, 'CODEX_OPS_STORE': str(root / 'cache'), 'CODEX_OPS_MEASUREMENT_ORIGIN': 'validation'}
            params = StdioServerParameters(command=sys.executable, args=[str(ROOT / 'server.py')], env=env)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    catalogue = await session.list_tools()
                    self.assertEqual(len(catalogue.tools), 6)
                    for tool in catalogue.tools:
                        self.assertNotIn('ctx', tool.input_schema.get('properties', {}))
                    result = await session.call_tool('ops_plan', {'root': str(root), 'operations': [
                        {'operation': 'write', 'args': {'path': 'a.txt', 'content': 'after'}}]})
                    self.assertFalse(result.is_error)
                    receipt = result.structured_content or json.loads(result.content[0].text)
                    self.assertEqual((root / 'a.txt').read_text(), 'before')
                    self.assertEqual(receipt['kind'], 'reference')
                    command = [receipt['nativeExecution']['executable'], *receipt['nativeExecution']['args']]
                    applied = await asyncio.to_thread(subprocess.run, command, capture_output=True, text=True, env=env, timeout=40)
                    self.assertEqual(applied.returncode, 0, applied.stderr + applied.stdout)
                    state = json.loads(applied.stdout)
                    self.assertEqual((root / 'a.txt').read_text(), 'after')
                    rollback = [sys.executable, str(ROOT / 'mutations/__main__.py'), 'rollback', '--root', str(root), '--id', state['journalId']]
                    restored = await asyncio.to_thread(subprocess.run, rollback, capture_output=True, text=True, env=env, timeout=40)
                    self.assertEqual(restored.returncode, 0, restored.stderr + restored.stdout)
                    self.assertTrue(json.loads(restored.stdout)['rollbackComplete'])
                    self.assertEqual((root / 'a.txt').read_text(), 'before')


if __name__ == '__main__':
    unittest.main()
