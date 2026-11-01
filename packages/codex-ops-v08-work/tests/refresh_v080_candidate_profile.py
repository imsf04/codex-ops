"""Refresh only the private candidate native plugin after a source freeze."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

from prepare_v080_profiles import PRIVATE, ROOT, native, trust_hooks
from host_rpc import call
from native_cli import mcp_python


def hashes(path):
    return {p.relative_to(path).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'prepared':True,'paidModelCalls':0,'mutations':False}))
        return
    area = PRIVATE/'0.8.0'
    home = area/'home'
    package = area/'marketplace/plugins/codex-ops'
    cache = home/'plugins/cache'
    baseline_paths = [cache/f'codex-ops-acceptance-{v}' for v in ('061','070')]
    before = {str(path):hashes(path) for path in baseline_paths}
    archive = area/'profile-refreshes'/str(time.time_ns())
    archive.mkdir(parents=True)
    shutil.copytree(package,archive/'descriptor-before')
    shutil.copytree(cache/'codex-ops-acceptance-080',archive/'cached-before')
    shutil.copy2(home/'config.toml',archive/'config-before.toml')
    for name in ('.codex-plugin','skills'):
        shutil.copytree(ROOT/name,package/name,dirs_exist_ok=True)
    previous_mcp = json.loads((package/'.mcp.json').read_text())['mcpServers']['codex_ops']
    settings = json.loads((ROOT/'.mcp.json').read_text())
    server = settings['mcpServers']['codex_ops']
    for key in ('args','env_vars'):
        server[key] = previous_mcp[key]
    (package/'.mcp.json').write_text(json.dumps(settings,indent=2),encoding='utf-8')
    definitions = json.loads((ROOT/'hooks/hooks.json').read_text())
    command = '& "'+str(mcp_python()).replace('\\','/')+'" "'+str(ROOT/'hook.py').replace('\\','/')+'"'
    for groups in definitions['hooks'].values():
        for group in groups:
            for hook in group['hooks']:
                hook['command'] = command
                hook['commandWindows'] = command
    (package/'hooks/hooks.json').write_text(json.dumps(definitions,indent=2),encoding='utf-8')
    env = {**os.environ,'CODEX_HOME':str(home)}
    plugin = 'codex-ops@codex-ops-acceptance-080'
    installed = native(['plugin','add',plugin,'--json'],env)
    enabled = call('config/value/write',{'keyPath':'plugins.'+json.dumps(plugin)+'.enabled',
                   'mergeStrategy':'upsert','value':True},env,str(PRIVATE))
    assert 'error' not in enabled, enabled
    try:
        trusted = trust_hooks(env)
        hooks = [h for group in trusted['result']['data'] for h in group['hooks']
                 if 'codex-ops-acceptance-080' in json.dumps(h)]
        assert len(hooks)==2 and all(h['trustStatus']=='trusted' and h['enabled'] for h in hooks)
    finally:
        disabled = call('config/value/write',{'keyPath':'plugins.'+json.dumps(plugin)+'.enabled',
                        'mergeStrategy':'upsert','value':False},env,str(PRIVATE))
        assert 'error' not in disabled, disabled
    cached_skill = cache/'codex-ops-acceptance-080/codex-ops/0.8.0/skills/compact-output/SKILL.md'
    source_skill = ROOT/'skills/compact-output/SKILL.md'
    assert cached_skill.read_bytes()==source_skill.read_bytes()
    assert before=={str(path):hashes(path) for path in baseline_paths}
    receipt = {'paidModelCalls':0,'archive':str(archive),'installed':installed,
               'hooks':hooks,'baselineCacheUnchanged':True,'candidateDefaultEnabled':False,
               'cachedSkillSha256':hashlib.sha256(cached_skill.read_bytes()).hexdigest(),
               'descriptorSha256':hashes(package),'cachedSha256':hashes(cache/'codex-ops-acceptance-080')}
    path = archive/'receipt.json'
    path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({'receipt':str(path),'baselineCacheUnchanged':True,'trustedHooks':len(hooks),
                      'cachedSkillSha256':receipt['cachedSkillSha256'],'paidModelCalls':0}))


if __name__ == '__main__':
    main()
