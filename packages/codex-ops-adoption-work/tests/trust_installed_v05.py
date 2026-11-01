"""Register the reviewed 0.5 package through the native config API."""
import json
from pathlib import Path
import shutil
from host_rpc import call

root = Path(__file__).resolve().parents[1]
backup = root / 'verification/config-before-0.5.0.toml'
assert not backup.exists(), 'Retain original backup'
shutil.copy2(Path.home() / '.codex/config.toml', backup)
result = call('hooks/list', {})
hooks = [h for group in result['result']['data'] for h in group['hooks']
         if h.get('pluginId') == 'codex-ops@personal']
assert len(hooks) == 2
updates = []
for hook in hooks:
    assert '\\0.5.0\\' in hook['sourcePath'] and hook['enabled']
    definition, content = hook['currentHash'].split('/')
    key = 'hooks.state.' + json.dumps(hook['key'])
    updates.append(call('config/value/write', {'keyPath': key,
        'mergeStrategy': 'upsert', 'value': {'trusted_hash': definition,
                                           'trusted_content_hash': content}}))
    assert 'error' not in updates[-1], updates[-1]
after = call('hooks/list', {})
owned = [h for group in after['result']['data'] for h in group['hooks']
         if h.get('pluginId') == 'codex-ops@personal']
assert len(owned) == 2 and all(h['trustStatus'] == 'trusted' and h['enabled'] for h in owned), after
(root / 'verification/native-hooks-0.5.0.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
print(json.dumps({'trusted': len(owned), 'nativeConfigurationAPI': True}))
