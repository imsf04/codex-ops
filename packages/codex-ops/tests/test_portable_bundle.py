import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import portable_install
import owned_process
from scripts import build_portable


class PortableBundleTests(unittest.TestCase):
    def test_owned_installation_process_cleans_up_background_children(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ready, escaped = root / 'ready', root / 'escaped'
            child = ('from pathlib import Path; import sys,time; '
                     'Path(sys.argv[1]).touch(); time.sleep(1); Path(sys.argv[2]).touch()')
            parent = '''import pathlib, subprocess, sys, time
subprocess.Popen([sys.executable, '-c', *sys.argv[1:]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
deadline = time.monotonic() + 5
while not pathlib.Path(sys.argv[2]).exists():
    if time.monotonic() > deadline:
        raise RuntimeError('child did not start')
    time.sleep(.01)
'''
            owned_process.run([sys.executable, '-c', parent, child, str(ready), str(escaped)],
                              env=os.environ.copy(), check=True, timeout=10)
            self.assertTrue(ready.exists())
            time.sleep(1.2)
            self.assertFalse(escaped.exists())

    def test_bundle_includes_runtime_sources_and_binds_to_extraction_path(self):
        with tempfile.TemporaryDirectory(prefix='codex ops bundle ') as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            for name in ('LICENSE', 'NOTICE'):
                (root / name).write_text('original attribution ' + name, encoding='utf-8')
            (root / 'licenses').mkdir()
            (root / 'licenses/native.txt').write_text('native license', encoding='utf-8')
            for name in ('.codex-plugin', 'hooks', 'skills', 'mutations', 'runtime_bridge', 'experimental', 'docs', 'bin'):
                (source / name).mkdir()
            for name in ('server.py', 'hook.py', 'portable_install.py', 'pyproject.toml', 'uv.lock',
                         'LICENSE', 'README.md', 'README.zh-CN.md'):
                (source / name).write_text('fixture', encoding='utf-8')
            (source / 'hooks/hooks.json').write_text(json.dumps({'hooks': {'SessionStart': [
                {'hooks': [{'type': 'command', 'command': 'old machine path'}]}]}}), encoding='utf-8')
            (source / 'runtime_bridge/launcher_posix.py').write_text('fixture', encoding='utf-8')
            for name in ('portable-package.md', 'portable-package.zh-CN.md'):
                (source / 'docs' / name).write_text('installation instructions', encoding='utf-8')
            suffix = '.exe' if os.name == 'nt' else ''
            for name in ('dsh-ops-worker', 'codex-ops-kernel'):
                (source / 'bin' / (name + suffix)).write_bytes(b'fixture')
            if os.name == 'nt':
                (source / 'bin/codex-ops-cli.exe').write_bytes(b'fixture')
            uv = root / 'uv'
            uv.write_bytes(b'fixture')
            with patch.object(build_portable, 'SOURCE', source), patch.object(build_portable, 'REPOSITORY', root):
                bundle = build_portable.build(root / 'extract here', uv)
            self.assertEqual((bundle / 'NOTICE').read_text(), 'original attribution NOTICE')
            self.assertEqual((bundle / 'LICENSE').read_text(), 'original attribution LICENSE')
            self.assertEqual((bundle / 'licenses/native.txt').read_text(), 'native license')
            plugin = bundle / 'plugin'
            initial_hooks = json.loads((plugin / 'hooks/hooks.json').read_text())
            initial_command = initial_hooks['hooks']['SessionStart'][0]['hooks'][0]['command']
            self.assertNotIn('old machine path', initial_command)
            python = root / 'interpreter'
            if os.name == 'nt':
                python.write_bytes(b'fixture')
            else:
                actual = root / 'actual-interpreter'
                actual.write_bytes(b'fixture')
                python.symlink_to(actual)
            descriptor = portable_install.configure(plugin, python)
            self.assertEqual(descriptor['mcpServers']['codex_ops']['command'], str(python.absolute()))
            self.assertEqual(descriptor['mcpServers']['codex_ops']['args'][-1], str((plugin / 'server.py').resolve()))
            hook = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks']['SessionStart'][0]['hooks'][0]
            self.assertIn(str(python.absolute()), hook['command'])
            self.assertIn(str((plugin / 'hook.py').resolve()), hook['command'])
            self.assertNotIn('old machine path', hook['command'])
            if os.name != 'nt':
                launcher = plugin / 'bin/codex-ops-cli'
                self.assertTrue(os.access(launcher, os.X_OK))
                self.assertIn(str(python.absolute()), launcher.read_text(encoding='utf-8'))
                self.assertIn(str(plugin / 'runtime_bridge/launcher_posix.py'), launcher.read_text(encoding='utf-8'))
            index = json.loads((bundle / '.agents/plugins/marketplace.json').read_text())
            self.assertEqual(index['plugins'][0]['source']['path'], './plugin')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                build_portable.build(bundle, uv)


if __name__ == '__main__':
    unittest.main()
