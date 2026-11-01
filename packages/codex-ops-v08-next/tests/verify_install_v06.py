"""Inspect and enable the user-authorized native local plugin release."""
import json
from pathlib import Path
import shutil
from host_rpc import call

root = Path(__file__).resolve().parents[1]
folder = root / 'verification'
backup = folder / 'config-before-0.6.0.toml'
assert not backup.exists(), 'Preserve the original configuration backup'
shutil.copy2(Path.home() / '.codex/config.toml', backup)
before = call('hooks/list', {})
owned = [hook for group in before['result']['data'] for hook in group['hooks']
         if hook.get('pluginId') == 'codex-ops@personal']
assert len(owned) == 2
for hook in owned:
    assert '\\0.6.0\\' in hook['sourcePath'], hook['sourcePath']
    definition, contents = hook['currentHash'].split('/')
    update = call('config/value/write', {'keyPath': 'hooks.state.' + json.dumps(hook['key']),
        'mergeStrategy': 'upsert', 'value': {'trusted_hash': definition, 'trusted_content_hash': contents}})
    assert 'error' not in update, update
after = call('hooks/list', {})
hooks = [hook for group in after['result']['data'] for hook in group['hooks']
         if hook.get('pluginId') == 'codex-ops@personal']
assert len(hooks) == 2 and all(hook['enabled'] and hook['trustStatus'] == 'trusted' for hook in hooks)
(folder / 'native-hooks-0.6.0.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
print(json.dumps({'trustedHooks': len(hooks)}), flush=True)
status = call('mcpServerStatus/list', {})
servers = [item for item in status['result']['data'] if item.get('pluginId') == 'codex-ops@personal' or item['name'] == 'codex_ops']
assert len(servers) == 1 and servers[0]['toolsError'] is None, servers
server = servers[0]
assert len(server['tools']) == 8
assert all('ctx' not in tool['inputSchema'].get('properties', {}) for tool in server['tools'].values())
(folder / 'native-mcp-0.6.0.json').write_text(json.dumps(server, indent=2), encoding='utf-8')
print(json.dumps({'tools': list(server['tools']), 'toolsError': server['toolsError']}), flush=True)
