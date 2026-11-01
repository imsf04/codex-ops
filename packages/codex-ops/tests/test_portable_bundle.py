import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import portable_install
from scripts import build_portable


class PortableBundleTests(unittest.TestCase):
    def test_bundle_includes_runtime_sources_and_binds_to_extraction_path(self):
        with tempfile.TemporaryDirectory(prefix='codex ops bundle ') as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            for name in ('.codex-plugin', 'hooks', 'skills', 'mutations', 'runtime_bridge', 'experimental', 'docs', 'bin'):
                (source / name).mkdir()
            for name in ('server.py', 'hook.py', 'portable_install.py', 'pyproject.toml', 'uv.lock',
                         'LICENSE', 'README.md', 'README.zh-CN.md'):
                (source / name).write_text('fixture', encoding='utf-8')
            (source / 'hooks/hooks.json').write_text(json.dumps({'hooks': {'SessionStart': [
                {'hooks': [{'type': 'command', 'command': 'old machine path'}]}]}}), encoding='utf-8')
            for name in ('portable-package.md', 'portable-package.zh-CN.md'):
                (source / 'docs' / name).write_text('installation instructions', encoding='utf-8')
            suffix = '.exe' if os.name == 'nt' else ''
            for name in ('dsh-ops-worker', 'codex-ops-kernel'):
                (source / 'bin' / (name + suffix)).write_bytes(b'fixture')
            if os.name == 'nt':
                (source / 'bin/codex-ops-cli.exe').write_bytes(b'fixture')
            uv = root / 'uv'
            uv.write_bytes(b'fixture')
            with patch.object(build_portable, 'SOURCE', source):
                bundle = build_portable.build(root / 'extract here', uv)
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
            index = json.loads((bundle / '.agents/plugins/marketplace.json').read_text())
            self.assertEqual(index['plugins'][0]['source']['path'], './plugin')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                build_portable.build(bundle, uv)


if __name__ == '__main__':
    unittest.main()
