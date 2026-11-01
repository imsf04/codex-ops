import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ENTRY = Path(__file__).resolve().parents[1] / 'runtime_bridge/control.py'
if os.name == 'nt':
    spec = importlib.util.spec_from_file_location('runtime_control', ENTRY)
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)


@unittest.skipUnless(os.name == 'nt', 'Windows registry and Desktop control')
class ControlTests(unittest.TestCase):
    def test_runtime_settings_accept_explicit_installed_python(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python = root / 'python.exe'
            native = root / 'native.exe'
            python.write_bytes(b'python')
            native.write_bytes(b'native')
            with patch.dict(os.environ, {'CODEX_OPS_BRIDGE_PYTHON': str(python)}), \
                    patch.object(control, '_native_cli', return_value=native):
                self.assertEqual(control._runtime_settings()['bridge-python.txt'], str(python))

    def test_immutable_bundle_and_enable_verify_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(control, 'DESTINATION', root):
                control.stage()
                control.stage()
                self.assertEqual((root / 'bin/codex.exe').read_bytes(), (root / 'bin/codex-ops-cli.exe').read_bytes())
                (root / 'store.py').write_text('modified')
                with self.assertRaisesRegex(ValueError, 'already differs'):
                    control.stage()
                with self.assertRaisesRegex(ValueError, 'changed after validation'):
                    control.enable()

    def test_enable_is_idempotent_and_rollback_restores_previous_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = {'value': '%USERPROFILE%/previous-cli.exe', 'type': control.winreg.REG_EXPAND_SZ}
            state = dict(previous)
            def write(value):
                state.update(value)
            with patch.object(control, 'DESTINATION', root), patch.object(control, 'BASE', root), \
                    patch.object(control, 'user_environment', side_effect=lambda: dict(state)), \
                    patch.object(control, 'write_environment', side_effect=write):
                control.stage()
                control.enable()
                control.enable()
                self.assertEqual(json.loads((root / 'environment-before.json').read_text()), previous)
                self.assertEqual(state['value'], str(root / 'bin/codex-ops-cli.exe'))
                control.rollback()
                self.assertEqual(state, previous)
                self.assertTrue((root / 'store.py').is_file())
                with self.assertRaisesRegex(ValueError, 'changed separately'):
                    control.rollback()

    def test_desktop_override_resolves_native_cli_without_path_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native = root / 'native.exe'
            native.write_bytes(b'fixture')
            wrapper = root / 'codex-ops-cli.exe'
            wrapper.write_bytes(b'fixture')
            (root / 'real-cli.txt').write_text(str(native))
            with patch.object(control, 'DESTINATION', root / 'bundle'), \
                    patch.object(control.shutil, 'which', return_value=None), \
                    patch.dict(control.os.environ, {'CODEX_APP_RUNTIME_CLI_PATH': str(wrapper)}):
                control.stage()
                actual = (root / 'bundle/bin/real-cli.txt').read_text().strip()
                self.assertEqual(actual, str(native))


if __name__ == '__main__':
    unittest.main()
