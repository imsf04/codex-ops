"""Refresh private native plugin descriptors with explicit measurement forwarding."""
import json
import os
from pathlib import Path

from prepare_v080_profiles import PRIVATE, native, trust_hooks

for version in ('0.6.1','0.7.0','0.8.0'):
    area = PRIVATE/version
    profile = json.loads((area/'profile.json').read_text(encoding='utf-8'))
    path = area/'marketplace/plugins/codex-ops/.mcp.json'
    original = path.read_text(encoding='utf-8')
    backup = area/'mcp-before-measurement-env.json'
    if not backup.exists():
        backup.write_text(original,encoding='utf-8')
    settings = json.loads(original)
    settings['mcpServers']['codex_ops']['env_vars'] = ['CODEX_OPS_STORE','CODEX_OPS_MEASUREMENT_ORIGIN']
    path.write_text(json.dumps(settings,indent=2),encoding='utf-8')
    env = {**os.environ,'CODEX_HOME':profile['home']}
    name = 'codex-ops@codex-ops-acceptance-'+version.replace('.','')
    result = native(['plugin','add',name,'--json'],env)
    (area/'measurement-env-install.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    hooks = trust_hooks(env)
    owned = [hook for group in hooks['result']['data'] for hook in group['hooks'] if 'codex-ops' in json.dumps(hook)]
    assert len(owned)==2 and all(h['enabled'] and h['trustStatus']=='trusted' for h in owned)
    (area/'measurement-env-hooks.json').write_text(json.dumps(hooks,indent=2),encoding='utf-8')
    print(json.dumps({'version':version,'forwarded':['CODEX_OPS_STORE','CODEX_OPS_MEASUREMENT_ORIGIN']}),flush=True)
