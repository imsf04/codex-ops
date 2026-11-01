import json
import os
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

import probe_app_server as probe
import v080_native_probe
import workflow_view


class SharedHomeProbeTests(unittest.TestCase):
    def test_override_values_preserve_toml_types_and_unquoted_cli_keys(self):
        values = {'model_providers': {'probe': {'name': '本地 "probe"', 'requires_openai_auth': False}},
                  'array': [{'path': r'C:\fixture', 'nested': [1, True]}], 'empty': {}}
        entries = list(probe.config_entries(values))
        self.assertIn('model_providers.probe.requires_openai_auth=false', entries)
        self.assertTrue(all(not entry.startswith('"') for entry in entries))
        for entry in entries:
            _, value = entry.split('=', 1)
            tomllib.loads('value=' + value)
        plugin = list(probe.config_entries({'plugins': {'codex-ops@fixture': {'enabled': True}}}))
        self.assertEqual(plugin, ['plugins.codex-ops@fixture.enabled=true'])
        for key in ('literal.dot', 'quote"key'):
            with self.assertRaises(ValueError):
                list(probe.config_entries({key: True}))

    def test_shared_home_configuration_is_process_only(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / 'config.toml').write_text('[mcp_servers.unrelated]\ncommand="unused"\n')
            (home / 'auth.json').write_text(json.dumps({'fixture': True}))
            before = probe.home_inputs(home)
            command = ['shim.exe', 'app-server', '--stdio']
            environment = {'CODEX_HOME': 'wrong', 'CODEX_OPS_AUTO_OUTPUT': 'inherited',
                           'CODEX_OPS_BRIDGE_MANAGER_PID': 'old', 'CODEX_OPS_BRIDGE_SHIM_PID': 'old'}
            config = 'sandbox_mode="workspace-write"\n[windows]\nsandbox="elevated"\n[mcp_servers.probe]\ncommand="python"\n'
            with patch('run_model_benchmark.flags', return_value=['-c', 'features.plugins=false']):
                probe.shared_config(command, environment, home, config)
            self.assertEqual(probe.home_inputs(home), before)
            self.assertEqual(environment, {'CODEX_HOME': str(home)})
            self.assertIn('mcp_servers.unrelated.enabled=false', command)
            self.assertIn('mcp_servers.probe.enabled=true', command)
            self.assertIn('sandbox_mode="workspace-write"', command)
            self.assertEqual(command[-2:], ['app-server', '--stdio'])

    def test_v080_marker_follows_original_exact_roundtrip_assertion(self):
        with tempfile.TemporaryDirectory() as directory:
            script = v080_native_probe.source(Path(directory) / 'fixture')
        self.assertLess(script.index('V070_OBSERVATION_ROUNDTRIP_FAILED'), script.index('V080_NATIVE_OBSERVATIONS_EXACT'))
        self.assertLess(script.index('V080_REUSE_FAILED'), script.index('V080_NATIVE_OBSERVATIONS_EXACT'))
        self.assertNotIn("'runs.txt'", script)
        self.assertIn('/runs.txt', script)
        value = {'kind': 'workflow-view', 'operation': 'verify', 'exitCode': 2,
                 'diagnostics': ['VERIFY_070_SENTINEL']}
        result = v080_native_probe.presentation([{'output': [{'type': 'text', 'text': json.dumps(value)}]}])
        self.assertTrue(result['verificationFailureVisible'])
        self.assertEqual(result['directOperations'], ['verify'])

    def test_fresh_recovery_requires_structured_source_and_distinct_attested_revision(self):
        value = {'kind': 'evidence-packet', 'operation': 'working_set', 'items': [{
            'kind': 'working-source', 'state': 'stale', 'source': {'path': 'settings.py', 'revision': 'old'},
            'currentRevision': 'new', 'currentEvidence': {'status': 'completed', 'path': 'settings.py',
            'revision': 'new', 'items': [{'line': 1, 'text': 'POLICY_ALPHA = "V080_FRESH_SOURCE"'}]}}]}
        def delivered(payload):
            outputs = [{'output': [{'type': 'text', 'text': json.dumps(payload)}]}]
            return v080_native_probe.presentation(outputs)['freshRecoveryVisible']
        self.assertTrue(delivered(value))
        self.assertTrue(delivered(workflow_view.project(value)))
        self.assertFalse(delivered({'kind': 'workflow-view', 'operation': 'working_set',
                                    'text': 'V080_STALE_CURRENT_RECOVERY V080_FRESH_SOURCE'}))
        value['items'][0]['currentRevision'] = 'wrong'
        self.assertFalse(delivered(value))
        value['items'][0]['currentRevision'] = 'new'
        value['items'][0]['currentEvidence']['items'].append({'line': 2, 'text': 'POLICY_ALPHA = "allow"'})
        self.assertFalse(delivered(value))
        self.assertFalse(delivered(workflow_view.project(value)))


if __name__ == '__main__':
    unittest.main()
