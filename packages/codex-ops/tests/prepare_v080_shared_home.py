"""Share authoritative Windows sandbox state while selecting immutable plugin arms."""
import json
import os
from pathlib import Path

from host_rpc import call
from prepare_v080_profiles import PRIVATE, native

VERSIONS = ('0.6.1','0.7.0','0.8.0')
IDS = {version:'codex-ops@codex-ops-acceptance-'+version.replace('.','') for version in VERSIONS}


def setting(env, key, value):
    result = call('config/value/write',{'keyPath':key,'mergeStrategy':'upsert','value':value},env,str(PRIVATE))
    if 'error' in result:
        raise RuntimeError(str(result['error']))


def owned_hooks(result):
    return [hook for group in result['result']['data'] for hook in group['hooks']
            if any(hook['key'].startswith(plugin+':') for plugin in IDS.values())]


def main():
    home = PRIVATE/'0.8.0/home'
    backup = PRIVATE/'shared-home-config-before.toml'
    if not backup.exists():
        backup.write_bytes((home/'config.toml').read_bytes())
    env = {**os.environ,'CODEX_HOME':str(home),
           'CODEX_OPS_STORE':str(PRIVATE/'shared-bootstrap-store'),'CODEX_OPS_MEASUREMENT_ORIGIN':'validation'}
    installations = {}
    for version in VERSIONS:
        registered = native(['plugin','marketplace','add',str(PRIVATE/version/'marketplace'),'--json'],env)
        installed = native(['plugin','add',IDS[version],'--json'],env)
        installations[version] = {'registered':registered,'installed':installed}
        setting(env,'plugins.'+json.dumps(IDS[version])+'.enabled',True)
        print(json.dumps({'installed':version}),flush=True)
    before = call('hooks/list',{},env,str(PRIVATE))
    hooks = owned_hooks(before)
    assert len(hooks)==6, 'Expected two hooks for each of three private arms'
    for hook in hooks:
        definition,content = hook['currentHash'].split('/')
        setting(env,'hooks.state.'+json.dumps(hook['key']),
                {'trusted_hash':definition,'trusted_content_hash':content})
    trusted = call('hooks/list',{},env,str(PRIVATE))
    assert all(h['enabled'] and h['trustStatus']=='trusted' for h in owned_hooks(trusted))
    for plugin in IDS.values():
        setting(env,'plugins.'+json.dumps(plugin)+'.enabled',False)
    disabled = call('hooks/list',{},env,str(PRIVATE))
    assert not any(h['enabled'] for h in owned_hooks(disabled))
    mapping = {version:{'home':str(home),'pluginSelection':{plugin:plugin==IDS[version] for plugin in IDS.values()},
                        'serverName':'codex_ops'} for version in VERSIONS}
    (PRIVATE/'shared-profiles.json').write_text(json.dumps(mapping,indent=2),encoding='utf-8')
    receipt = {'home':str(home),'installations':installations,'before':before,'trusted':trusted,
               'defaultsDisabled':disabled,'sandboxProvisionedByThisScript':False,'paidModelCalls':0}
    (PRIVATE/'shared-bootstrap.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({'home':str(home),'profiles':3,'trustedHooks':6,'enabledByDefault':0,'needsOfficialSandboxSetup':True}),flush=True)


if __name__=='__main__':
    main()
