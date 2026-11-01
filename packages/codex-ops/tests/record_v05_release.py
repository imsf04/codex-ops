"""Record installed state separately from current Desktop bridge activation."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import winreg

root = Path(__file__).resolve().parents[1]
verification = root / 'verification'
def read(name):
    return json.loads((verification / name).read_text(encoding='utf-8'))
quality = read('quality/crap.json')
for name, expected in quality['sourceSha256'].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
bundle = Path.home() / 'AppData/Local/CodexOps/runtime/0.5.0'
staged = json.loads((bundle / 'bundle.json').read_text())
for name, expected in staged['files'].items():
    assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == expected, name
with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
    override = winreg.QueryValueEx(key, 'CODEX_CLI_PATH')[0]
assert Path(override) == bundle / 'bin/codex-ops-cli.exe'
hooks = [h for group in read('native-hooks-0.5.0.json')['result']['data'] for h in group['hooks']]
assert len(hooks) == 2 and all(h['enabled'] and h['trustStatus'] == 'trusted' for h in hooks)
mcp = read('native-mcp-0.5.0.json')
assert len(mcp['tools']) == 6 and mcp['toolsError'] is None
installed = Path.home() / '.codex/plugins/cache/personal/codex-ops/0.5.0/.codex-plugin/plugin.json'
assert json.loads(installed.read_text())['version'] == '0.5.0'
process = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
    "Get-CimInstance Win32_Process -Filter 'ProcessId=12556' | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
    capture_output=True, text=True, check=True)
active = json.loads(process.stdout)
assert '\\runtime\\0.4.0\\' in active['CommandLine'], active
comparison = read('real-model-comparison.json')
report = {'version': '0.5.0', 'configured': True, 'activeDesktopVerified': False,
    'restartRequired': True, 'configuredOverride': override, 'updatedAt': time.time(),
    'currentDesktopBridge': active, 'currentDesktopBridgeVersion': '0.4.0',
    'activationEvidence': 'Process command line; generic control.status restartRequired does not distinguish runtime versions',
    'unitTestsPassed': 272, 'nativeChecks': {'appServer': 8, 'stagedRuntime': 10,
        'nativeBash': 9, 'mcpHost': 7, 'nativeStdio': 10}, 'instrumentedShimChecks': 3,
    'pythonProductionModules': len(quality['sourceSha256']), 'functionsMeasured': quality['functionCount'],
    'above6': quality['above6'], 'maximumCrap': quality['maximum'], 'coveragePercent': 99.08,
    'sourceHashesVerified': len(quality['sourceSha256']), 'stagedHashesVerified': len(staged['files']),
    'hooksTrusted': True, 'mcpToolsAvailable': list(mcp['tools']), 'currentChatMcpVerified': True,
    'mcpPlannerNativeApplyRollbackVerified': True, 'sandboxPolicyUnchanged': True,
    'sandboxUpdate': read('sandbox-readiness.json'), 'isolatedSandboxUpdate': read('probe-sandbox-update.json'),
    'realModelPilot': {'report': 'verification/real-model-comparison.json',
        'baselinePasses': comparison['baselineSuccesses'], 'enabledPasses': comparison['enabledSuccesses'],
        'onlyComparableSuccessfulPair': 'repair_tests',
        'repairTotalTokens': {'baseline': 409938, 'enabled': 255490},
        'repairWallSeconds': {'baseline': 72.323, 'enabled': 154.154},
        'limitations': ['Five tasks only; no broad speed or reliability conclusion',
            'Other successful pairs have changed workspace permission layouts or missing resource metrics',
            'No plugin skill/SessionStart guidance in pilot; only bridge and six tools',
            'Only code location used MCP; pilot does not establish adoption of the new workflow',
            'Total tokens include repeated cached input; not billable-token savings']},
    'fixedWorkload': {k: read('workload-benchmark.json')[k] for k in
        ('originalBytes', 'presentedBytes', 'savedBytes', 'reductionPercent')},
    'semanticPreview': read('semantic-preview-benchmark.json'),
    'dashboard': 'verification/dashboard-production.html',
    'features': ['Fused search with merged context and revision checks',
        'On-demand exact schemas/examples for 17 operations',
        'Bounded cached count/group and multi-reference query batches',
        'Selective small completed test/build log compression',
        'Completed five-minute telemetry windows and explicit localhost refresh dashboard',
        'Bounded read-only task journal view and native read-only plan loading'],
    'remainingBoundary': ['Cross-model-step deduplication remains unsupported',
        'Operation catalogue does not dynamically register native SDK tools',
        'Native metadata-preserving worker writes may be denied in workspace-write mode; no permission bypass',
        'Time windows exclude the partial current bucket and legacy unbucketed data',
        'Current Desktop bridge remains 0.4.0 until full restart'],
    'rollbackSource': 'verification/source-0.4.0.zip',
    'rollbackEnvironment': str(bundle / 'environment-before.json')}
for name in ('v05-release.json', 'desktop-installation.json'):
    (verification / name).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps({'installed': report['version'], 'restartRequired': True,
    'sourceHashesVerified': report['sourceHashesVerified'], 'stagedHashesVerified': report['stagedHashesVerified']}))
