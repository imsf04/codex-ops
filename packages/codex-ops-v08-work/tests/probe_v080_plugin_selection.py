"""Read effective native plugin selection without starting a model turn."""
import json
from pathlib import Path
import time

from preflight_v080_profiles import PRIVATE, profile
from v080_native_host import NativeHost, flags

area = PRIVATE/('selection-probe-'+str(time.time_ns()))
workspace = area/'workspace'
workspace.mkdir(parents=True)
config = profile('0.6.1')
host = NativeHost(config,workspace,area/'store')
try:
    host.request('initialize',{'clientInfo':{'name':'v080-selection-probe','version':'0.8.0'},
                               'capabilities':{'experimentalApi':True}})
    host.send({'method':'initialized'})
    current = host.request('config/read',{'includeLayers':True})
    print(json.dumps({'flags':flags('medium',config),'plugins':current.get('config',{}).get('plugins'),
                      'features':current.get('config',{}).get('features')}),flush=True)
finally:
    host.close()
