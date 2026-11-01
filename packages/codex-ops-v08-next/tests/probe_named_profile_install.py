"""Observe official plugin config writes in an inert disposable home only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from native_cli import native_cli

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe',action='store_true')
    args = parser.parse_args()
    if not args.probe:
        print(json.dumps({'prepared':True,'globalMutations':False,'paidModelCalls':0}))
        return
    area = ROOT/'tests/next-profile-write-probe'
    assert not area.exists()
    assert area.resolve().is_relative_to((ROOT/'tests').resolve())
    home = area/'home'
    package = area/'marketplace/plugins/profile-write-probe'
    (package/'.codex-plugin').mkdir(parents=True)
    (package/'.codex-plugin/plugin.json').write_text(json.dumps({
        'name':'profile-write-probe','version':'0.0.0',
        'description':'Inert local metadata fixture; no tools, skills, or hooks.'}),encoding='utf-8')
    registry = area/'marketplace/.agents/plugins'
    registry.mkdir(parents=True)
    (registry/'marketplace.json').write_text(json.dumps({
        'name':'profile-write-probe-market','interface':{'displayName':'Inert profile write probe'},
        'plugins':[{'name':'profile-write-probe','source':{'source':'local','path':'./plugins/profile-write-probe'},
                    'policy':{'installation':'AVAILABLE','authentication':'ON_INSTALL'},'category':'Productivity'}]}),encoding='utf-8')
    home.mkdir()
    (home/'config.toml').write_text('approval_policy = "never"\n',encoding='utf-8')
    (home/'benchmark.config.toml').write_text('[features]\nplugins = true\n',encoding='utf-8')
    environment = {**os.environ,'CODEX_HOME':str(home)}
    for name in ('CODEX_APP_TOOLS_PIPE_PATH','CODEX_OPS_BRIDGE_MANAGER_PID','CODEX_OPS_BRIDGE_SHIM_PID'):
        environment.pop(name,None)
    executable = native_cli()
    commands = [ ['plugin','marketplace','add',str(area/'marketplace'),'--json'],
                 ['plugin','add','profile-write-probe@profile-write-probe-market','--json'] ]
    receipts = []
    for command in commands:
        process = subprocess.run([executable,'--profile','benchmark',*command],env=environment,
                                 cwd=area,capture_output=True,text=True,encoding='utf-8',timeout=60,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        receipts.append({'args':['--profile','benchmark',*command],'exitCode':process.returncode,
                         'stdout':process.stdout,'stderr':process.stderr,
                         'baseConfig':(home/'config.toml').read_text(),
                         'profileConfig':(home/'benchmark.config.toml').read_text()})
        if process.returncode:
            break
    result = {'nativeCli':executable,'nativeCliSha256':hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
              'home':str(home),'globalHomeUsed':False,'authCopied':False,'sandboxSetupCalls':0,
              'paidModelCalls':0,'hasSandboxSecretsDirectory':(home/'.sandbox-secrets').exists(),
              'commands':receipts}
    (area/'receipt.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'receipt':str(area/'receipt.json'),'commands':[{'exitCode':r['exitCode'],
                     'baseConfig':r['baseConfig'],'profileConfig':r['profileConfig']} for r in receipts]}))


if __name__=='__main__':
    main()
