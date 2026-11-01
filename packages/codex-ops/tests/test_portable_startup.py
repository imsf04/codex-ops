import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class PortableStartupTests(unittest.TestCase):
    def test_stdio_server_lists_tools_and_reads_a_file(self):
        async def check(root):
            source = Path(__file__).resolve().parents[1]
            env = {**os.environ, 'CODEX_OPS_STORE': str(root / 'store'), 'PYTHONUTF8': '1'}
            params = StdioServerParameters(command=sys.executable, args=[str(source / 'server.py')], env=env)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertIn('ops_files', [item.name for item in tools.tools])
                    result = await session.call_tool('ops_files', {
                        'root': str(root), 'operation': 'read',
                        'args': {'files': [{'path': 'sample.txt'}]},
                    })
                    self.assertFalse(result.is_error, result)
                    self.assertIn('portable stdio evidence', str(result))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sample.txt').write_text('portable stdio evidence\n', encoding='utf-8')
            asyncio.run(check(root))

    def test_bridge_and_snapshot_platform_support_is_explicit(self):
        import doctor
        import readonly_snapshot
        import runtime_status
        if os.name != 'nt':
            self.assertFalse(runtime_status.current()['activeForThisProcess'])
            self.assertIn('not available', doctor.report()['nextActions'][0])
            with self.assertRaisesRegex(OSError, 'not yet available'):
                with readonly_snapshot.database(Path('unused')):
                    self.fail('Unsupported snapshot must not execute')
        else:
            self.assertIsNotNone(doctor.control)
            self.assertTrue(callable(readonly_snapshot._locked_reader))


if __name__ == '__main__':
    unittest.main()
