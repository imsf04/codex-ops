"""No-model native profile and transparent MCP worker-observer checks."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from native_cli import mcp_python
from v080_native_host import NativeHost
from v080_metrics import measured_workers

PRIVATE = Path(os.environ['LOCALAPPDATA'])/'CodexOps/acceptance-0.8'


def value(result):
    return result.structured_content or json.loads(result.content[0].text)


async def read_server(source, workspace, store, observed):
    observer = ROOT/'tests/v080_observed_server.py'
    args = ['-u',str(observer),'--package',str(source)] if observed else ['-u',str(source/'server.py')]
    env = {**os.environ,'CODEX_OPS_STORE':str(store),'CODEX_OPS_MEASUREMENT_ORIGIN':'validation'}
    params = StdioServerParameters(command=str(mcp_python()),args=args,cwd=str(source),env=env)
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            catalogue = await session.list_tools()
            result = await session.call_tool('ops_files',{'operation':'read','root':str(workspace),
                'args':{'files':[{'path':'proof.txt','offset':1,'limit':10}]}})
            return {'toolNames':[tool.name for tool in catalogue.tools],'result':value(result)}


def profile(version):
    area = PRIVATE/version
    installed = json.loads((area/'profile.json').read_text(encoding='utf-8'))
    result = {'home':installed['home'],'package':installed['source'],'toolCount':8,
            'executable':str(Path(os.environ['LOCALAPPDATA'])/'CodexOps/runtime'/version/'bin/codex-ops-cli.exe'),
            'serverName':'codex_ops'}
    shared = PRIVATE/'shared-profiles.json'
    if shared.exists():
        result.update(json.loads(shared.read_text(encoding='utf-8'))[version])
    return result


def preflight(version):
    config = profile(version)
    area = PRIVATE/('preflight-'+version+'-'+str(time.time_ns()))
    workspace = area/'workspace'
    workspace.mkdir(parents=True)
    workspace = workspace.resolve()
    source = Path(config['package'])
    (workspace/'proof.txt').write_bytes(b'first line\nlast line\n')
    direct = asyncio.run(read_server(source,workspace,area/'direct-store',False))
    observed = asyncio.run(read_server(source,workspace,area/'observed-store',True))
    identical = direct == observed
    assert identical, 'Worker observer changed returned value or advertised tools'
    workers = measured_workers(area/'observed-store')
    assert workers['available'] and workers['starts']==1, workers
    record = {'version':version,'paidModelCalls':0,'profileHome':config['home'],
              'observerExactValueEquality':identical,'observerWorkers':workers,'root':str(area)}
    host = NativeHost(config,workspace,area/'native-store')
    try:
        host.open(workspace)
        selected = [name for name,enabled in config.get('pluginSelection',{}).items() if enabled]
        hooks = [hook for group in host.hooks['data'] for hook in group['hooks']
                 if 'codex-ops' in json.dumps(hook) and hook.get('enabled')]
        if selected:
            assert len(selected)==1 and all(hook['key'].startswith(selected[0]+':') for hook in hooks)
        record['hooksObserved'] = [{key:hook.get(key) for key in ('key','enabled','trustStatus')} for hook in hooks]
        assert len(hooks)==2 and all(h['enabled'] and h['trustStatus']=='trusted' for h in hooks)
        code = 'import sys,json;sys.path.insert(0,sys.argv[1]);import runtime_status;print(json.dumps(runtime_status.current()))'
        result = host.request('command/exec',{'command':[str(mcp_python()),'-I','-c',code,str(source)],
                              'cwd':str(workspace),'timeoutMs':30000},timeout=45)
        assert result['exitCode']==0, result
        runtime = json.loads(result['stdout'])
        assert runtime.get('runtimeVersion')==version and runtime.get('activeForThisProcess'), runtime
        record.update(nativeTools=host.candidate_tools,hooksTrusted=len(hooks),runtime=runtime,
                      pluginSelection=config.get('pluginSelection',{}),
                      eventsPath=str(host.events_path),passed=True)
    except Exception as exc:
        record.update(passed=False,error=str(exc),eventsPath=str(host.events_path))
        destination = ROOT/'verification'/('v080-profile-'+version+'-failed-'+str(time.time_ns())+'.json')
        destination.write_text(json.dumps(record,indent=2),encoding='utf-8')
        raise
    finally:
        host.close()
    destination = ROOT/'verification'/('v080-profile-'+version+'.json')
    destination.write_text(json.dumps(record,indent=2),encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('versions',nargs='+')
    args = parser.parse_args()
    for version in args.versions:
        result = preflight(version)
        print(json.dumps({key:result[key] for key in ('version','paidModelCalls','hooksTrusted','observerExactValueEquality')}),flush=True)


if __name__ == '__main__':
    main()
