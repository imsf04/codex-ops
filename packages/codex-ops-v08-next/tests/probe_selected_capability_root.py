"""No-model native probe of an inert selected plugin root in a disposable home."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

from native_cli import native_cli

ROOT = Path(__file__).resolve().parents[1]


def create(area):
    home, package, workspace = (area/name for name in ('home','plugin','workspace'))
    home.mkdir(parents=True)
    workspace.mkdir()
    (package/'.codex-plugin').mkdir(parents=True)
    (package/'skills/selected-root-probe').mkdir(parents=True)
    (package/'hooks').mkdir()
    (package/'.codex-plugin/plugin.json').write_text(json.dumps({
        'name':'selected-root-probe','version':'0.0.0','description':'Inert local native capability probe',
        'skills':'./skills'}),encoding='utf-8')
    (package/'skills/selected-root-probe/SKILL.md').write_text(
        '---\nname: selected-root-probe\ndescription: Inert selected root discovery probe.\n---\nReturn the probe marker.\n',encoding='utf-8')
    server = package/'server.py'
    server.write_text('from mcp.server import MCPServer\nm=MCPServer("selected-root-probe")\n'
                      '@m.tool()\ndef selected_root_probe_echo(value: str) -> str:\n    return value\n'
                      'm.run(transport="stdio")\n',encoding='utf-8')
    (package/'.mcp.json').write_text(json.dumps({'mcpServers':{'selected_root_probe':{
        'command':sys.executable,'args':['-u',str(server)]}}}),encoding='utf-8')
    hook = package/'hook.py'
    hook.write_text('import json\nprint(json.dumps({"hookSpecificOutput":{"hookEventName":"SessionStart",'
                    '"additionalContext":"SELECTED_ROOT_HOOK_PROBE"}}))\n',encoding='utf-8')
    command = '& "'+sys.executable.replace('\\','/')+'" "'+str(hook).replace('\\','/')+'"'
    (package/'hooks/hooks.json').write_text(json.dumps({'hooks':{'SessionStart':[{'hooks':[{
        'type':'command','command':command,'commandWindows':command}]}]}}),encoding='utf-8')
    (home/'config.toml').write_text('model = "gpt-6.1-terra"\napproval_policy = "never"\n'
        'sandbox_mode = "workspace-write"\n[features]\nplugins = true\napps = false\n'
        '[windows]\nsandbox = "elevated"\n',encoding='utf-8')
    return home, package, workspace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe',action='store_true')
    args = parser.parse_args()
    if not args.probe:
        print(json.dumps({'prepared':True,'paidModelCalls':0,'globalHomeUsed':False}))
        return
    area = ROOT/'tests/next-capability-root-probe-mcp2'
    assert not area.exists()
    assert area.resolve().is_relative_to((ROOT/'tests').resolve())
    home, package, workspace = create(area)
    environment = {**os.environ,'CODEX_HOME':str(home)}
    for name in ('CODEX_APP_TOOLS_PIPE_PATH','CODEX_OPS_BRIDGE_MANAGER_PID','CODEX_OPS_BRIDGE_SHIM_PID'):
        environment.pop(name,None)
    stderr = (area/'stderr.log').open('w',encoding='utf-8')
    process = subprocess.Popen([native_cli(),'app-server','--stdio'],cwd=workspace,env=environment,
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,text=True,encoding='utf-8',
        creationflags=subprocess.CREATE_NO_WINDOW)
    inbox, messages = queue.Queue(), []
    def receive():
        for line in process.stdout:
            inbox.put(json.loads(line))
        inbox.put({'transportClosed':True})
    threading.Thread(target=receive,daemon=True).start()
    calls = []
    def request(method, params):
        number = len(calls)+1
        calls.append({'id':number,'method':method,'params':params})
        process.stdin.write(json.dumps({'id':number,'method':method,'params':params})+'\n')
        process.stdin.flush()
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            value = inbox.get(timeout=max(0.01,deadline-time.monotonic()))
            messages.append(value)
            if value.get('id')==number and 'method' not in value:
                return value
            if value.get('transportClosed'):
                raise RuntimeError('Native transport closed')
            if 'id' in value and 'method' in value:
                raise RuntimeError('Unexpected server request; no approvals are granted by this probe')
        raise TimeoutError(method)
    result = {'paidModelCalls':0,'sandboxSetupCalls':0,'globalHomeUsed':False,'authCopied':False,
              'package':str(package),'home':str(home)}
    try:
        result['initialize'] = request('initialize',{'clientInfo':{'name':'codex-ops-inert-root-probe','version':'0.1'},
                                      'capabilities':{'experimentalApi':True}})
        process.stdin.write('{"method":"initialized"}\n')
        process.stdin.flush()
        result['threadStart'] = request('thread/start',{'cwd':str(workspace),'model':'gpt-6.1-terra',
            'approvalPolicy':'never','sandbox':'workspace-write','ephemeral':True,
            'selectedCapabilityRoots':[{'id':'inert-selected-plugin','location':{
                'type':'environment','environmentId':'local','path':str(package)}}]})
        thread = result['threadStart'].get('result',{}).get('thread',{}).get('id')
        if thread:
            result['mcpStatus'] = request('mcpServerStatus/list',{'threadId':thread})
            result['skills'] = request('skills/list',{'cwds':[str(workspace)]})
            result['hooks'] = request('hooks/list',{'cwds':[str(workspace)]})
            result['threadRead'] = request('thread/read',{'threadId':thread,'includeTurns':True})
    except (OSError,RuntimeError,TimeoutError,queue.Empty) as error:
        result['error'] = type(error).__name__+': '+str(error)
    finally:
        process.terminate()
        process.wait(timeout=10)
        stderr.close()
        process.stdin.close()
        process.stdout.close()
        result['hasSandboxSecretsDirectory'] = (home/'.sandbox-secrets').exists()
        result['methodsSent'] = [call['method'] for call in calls]
        result['notifications'] = [m for m in messages if 'method' in m]
        assert 'turn/start' not in result['methodsSent']
        (area/'receipt.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'receipt':str(area/'receipt.json'),'error':result.get('error'),
                      'threadStartError':result.get('threadStart',{}).get('error'),
                      'mcpStatus':result.get('mcpStatus'),'paidModelCalls':0}))


if __name__=='__main__':
    main()
