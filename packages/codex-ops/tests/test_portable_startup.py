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
            root = Path(directory).resolve()
            (root / 'sample.txt').write_text('portable stdio evidence\n', encoding='utf-8')
            asyncio.run(check(root))

    def test_bridge_platform_support_is_explicit(self):
        import doctor
        import runtime_status
        if os.name != 'nt':
            self.assertFalse(runtime_status.current()['activeForThisProcess'])
            self.assertIn('not available', doctor.report()['nextActions'][0])
        else:
            self.assertIsNotNone(doctor.control)

    def test_directory_tasks_never_silently_bypass_platform_boundary(self):
        from mutations import task_directories
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            if os.name != 'nt':
                with self.assertRaisesRegex(OSError, 'not yet available'):
                    task_directories.execute(root, 'child', True)
                self.assertFalse((root / 'child').exists())
            else:
                task_directories.execute(root, 'child', True)
                self.assertTrue((root / 'child').is_dir())


if __name__ == '__main__':
    unittest.main()
