"""Isolate native command startup from Python imports and thread creation."""
import argparse
import json
from pathlib import Path
import time

from preflight_v080_profiles import PRIVATE, ROOT, profile
from v080_native_host import NativeHost

parser = argparse.ArgumentParser()
parser.add_argument('version')
args = parser.parse_args()
area = PRIVATE/('command-probe-'+args.version+'-'+str(time.time_ns()))
workspace = area/'workspace'
workspace.mkdir(parents=True)
workspace = workspace.resolve()
host = NativeHost(profile(args.version),workspace,area/'store')
record = {'version':args.version,'paidModelCalls':0,'root':str(area)}
try:
    host.request('initialize',{'clientInfo':{'name':'v080-command-probe','version':'0.8.0'},
                               'capabilities':{'experimentalApi':True}})
    host.send({'method':'initialized'})
    record['readiness'] = host.request('windowsSandbox/readiness',None)
    started = time.monotonic()
    record['command'] = host.request('command/exec',{'command':['C:/Windows/System32/cmd.exe','/d','/c','echo OPS_NATIVE_PREFLIGHT'],
                                    'cwd':str(workspace),'timeoutMs':10000},timeout=90)
    record['seconds'] = time.monotonic()-started
except Exception as exc:
    record['error'] = repr(exc)
finally:
    host.close()
(ROOT/'verification'/('v080-command-probe-'+args.version+'-'+str(time.time_ns())+'.json')).write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record),flush=True)
