import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import doctor
from runtime_bridge import control


class DoctorTests(unittest.TestCase):
    def test_configured_runtime_never_implies_current_chat_activation(self):
        root = Path(__file__).resolve().parents[1]
        expected = json.loads((root / '.codex-plugin/plugin.json').read_text())['version']
        selected = f'C:/CodexOps/runtime/{expected}/bin/codex.exe'
        with patch.object(control, 'user_environment', return_value={'value': selected}):
            for active_version in ('0.5.0', None):
                with patch.object(doctor.runtime_status, 'current', return_value={
                    'activeForThisProcess': True, 'runtimeVersion': active_version}):
                    result = doctor.report()
                    self.assertTrue(result['restartRequired'])
                    self.assertIn('Fully quit', result['nextActions'][0])
            with patch.object(doctor.runtime_status, 'current', return_value={
                'activeForThisProcess': True, 'runtimeVersion': expected}):
                result = doctor.report()
                self.assertFalse(result['restartRequired'])
                self.assertEqual(result['nextActions'], [])
        self.assertIsNone(doctor._configured_version(None))
        self.assertIn('Configure', doctor._actions(expected, None, {})[0])
        self.assertIn('Validate', doctor._actions(expected, expected, {'runtimeVersion': expected})[0])

    def test_bundle_mismatch_and_missing_bundle_are_explicit(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            with patch.object(control, 'BASE', base):
                self.assertFalse(doctor._bundle(base, '0.6.0')['available'])
                folder = base / 'runtime/0.6.0'
                folder.mkdir(parents=True)
                (folder / 'a').write_bytes(b'correct')
                (folder / 'bundle.json').write_text(json.dumps({'files': {
                    'a': hashlib.sha256(b'correct').hexdigest(), 'missing': 'wrong'}}))
                report = doctor._bundle(base, '0.6.0')
                self.assertFalse(report['valid'])
                self.assertEqual(report['mismatchedFiles'], ['missing'])
                (folder / 'a').write_bytes(b'changed')
                self.assertEqual(doctor._bundle(base, '0.6.0')['mismatchedFiles'], ['a', 'missing'])

    def test_global_status_checks_runtime_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            (base / 'bridge').mkdir()
            (base / 'bridge/x.json').write_text('{}')
            with patch.object(control, 'BASE', base), patch.object(control, 'user_environment', return_value={'value': 'selected'}):
                with patch.object(control, '_active_instance', return_value={'runtimeVersion': '0.5.0'}):
                    with patch.object(control.runtime_status, 'current', return_value={'runtimeVersion': '0.5.0'}):
                        self.assertTrue(control.status()['restartRequired'])
                with patch.object(control, '_active_instance', return_value={'runtimeVersion': control.VERSION}):
                    with patch.object(control.runtime_status, 'current', return_value={'runtimeVersion': '0.5.0'}):
                        self.assertTrue(control.status()['restartRequired'])
                    with patch.object(control.runtime_status, 'current', return_value={'runtimeVersion': control.VERSION}):
                        self.assertFalse(control.status()['restartRequired'])

    def test_expanded_catalogue_has_executable_task_and_sdk_contracts(self):
        import catalog
        task = catalog.describe('task')
        self.assertEqual(task['planArguments']['args']['stages'][0][0]['operation'], 'mkdir')
        self.assertEqual(len(task['operationSchemas']), 11)
        import workflow
        sdk = catalog.describe('workflows')['sdk']
        result = workflow.run(str(Path.cwd()), sdk['operation'], sdk['args'], 'test-owner')
        self.assertIn('function createOps', result['javascript'])


if __name__ == '__main__':
    unittest.main()
