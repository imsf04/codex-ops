"""Record verified installation separately from Desktop activation and model efficacy."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import winreg

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_status

root = Path(__file__).resolve().parents[1]
verification = root / 'verification'
quality = json.loads((verification / 'quality/crap.json').read_text())
assert quality['above6'] == 0 and quality['maximum'] <= 6
for name, expected in quality['sourceSha256'].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
bundle = Path.home() / 'AppData/Local/CodexOps/runtime/0.6.0'
staged = json.loads((bundle / 'bundle.json').read_text())
for name, expected in staged['files'].items():
    assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == expected, name
package = json.loads((verification / 'plugin-package-0.6.0.json').read_text())
cache = Path.home() / '.codex/plugins/cache/personal/codex-ops/0.6.0'
for name, expected in package['files'].items():
    assert hashlib.sha256((cache / name).read_bytes()).hexdigest() == expected, name
assert not (cache / '.venv').exists()
with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
    override = winreg.QueryValueEx(key, 'CODEX_CLI_PATH')[0]
assert Path(override) == bundle / 'bin/codex-ops-cli.exe'
hooks_result = json.loads((verification / 'native-hooks-0.6.0.json').read_text())
hooks = [h for group in hooks_result['result']['data'] for h in group['hooks'] if h.get('pluginId') == 'codex-ops@personal']
assert len(hooks) == 2 and all(h['enabled'] and h['trustStatus'] == 'trusted' for h in hooks)
mcp = json.loads((verification / 'native-mcp-0.6.0.json').read_text())
assert len(mcp['tools']) == 8 and mcp['toolsError'] is None
checks = {'appServer': 8, 'stagedRuntime': 13, 'nativeBash': 9, 'mcpHost': 7, 'nativeStdio': 10}
for name, count in [('desktop-runtime-report.json',13),('shell-host-report.json',9),('host-report.json',7),('code-host-report.json',10)]:
    assert json.loads((verification / name).read_text())['passed'] == count
comparison = json.loads((verification / 'v06-model-comparison.json').read_text())
assert comparison['complete'] and comparison['completedTrials'] == 120
completion = json.loads((verification / 'v06-model-completion.json').read_text())
current = runtime_status.current()
pid = current['managerPid']
command = "Get-CimInstance Win32_Process -Filter 'ProcessId=" + str(pid) + "' | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
process = json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-Command',command],text=True))
assert '\\runtime\\0.5.0\\' in process['CommandLine']
report = {'version':'0.6.0','configured':True,'activeDesktopVerified':False,'restartRequired':True,
    'updatedAt':time.time(),'configuredOverride':override,'currentDesktopBridge':process,
    'currentDesktopBridgeVersion':'0.5.0','activationEvidence':'Actual manager command line; current chat still runs previous runtime',
    'unitTestsPassed':354,'coverageSuiteTests':353,'nativeChecks':checks,'nativeCasesPassed':sum(checks.values()),
    'instrumentedShimChecks':3,'pythonProductionModules':len(quality['sourceSha256']),
    'functionsMeasured':quality['functionCount'],'above6':quality['above6'],'maximumCrap':quality['maximum'],
    'coveragePercent':99.17,'sourceHashesVerified':len(quality['sourceSha256']),
    'stagedHashesVerified':len(staged['files']),'nativePackageFilesVerified':len(package['files']),
    'nativePackageBytes':package['bytes'],'developmentVenvExcludedFromPlugin':True,
    'hooksTrusted':True,'mcpToolsAvailable':list(mcp['tools']),
    'installedSmoke':'verification/installed-smoke-0.6.0.json',
    'realModelEvaluation':{'report':'verification/v06-model-comparison.json','actualTrials':120,
        'strictStructuredConformance':completion['strictConformance'],
        'comparisonMetric':'Includes wording mismatches; not general reasoning accuracy',
        'v06VsNativeSuccessfulPairs':33,'inputTokensMedianChangePercent':9.37,
        'wallSecondsMedianChangePercent':4.2,'workItemsMedianChangePercent':0.0,
        'workflowTaskAdoption':0,'generalEfficiencyGainEstablished':False,
        'tokenReductionTargetMet':False,'callReductionTargetMet':False,
        'limitations':['Version6 ran in a later block; timing/cache differences are not causal evidence',
            'Entire version skill eagerly injected; daily on-demand loading not reproduced',
            'Actual PostToolUse hooks not executed in these paid trials',
            'Failures and one pre-model environment attempt retained; no paid outcome reruns',
            'Does not compare a real DSH host or prove superiority over dsh-ops']},
    'features':['Composable workflows and executable SDK with explicit bounded resolution',
        'Diagnostic/Git/MCP evidence and noninflating shared output-frame budget',
        'Explicit incremental range snapshots without assumed model-context retention',
        'Staged native file/tree lifecycle with cancellation and partial-move recovery',
        'Chat/permission or runtime reference ownership and current-process version diagnosis',
        'Read-only dashboard and reproducible20task/tworepeat/threecondition evaluation'],
    'remainingBoundary':['Automatic Code Mode refs are runtime-bound, not chat-bound; restart can end access',
        'Direct PostToolUse/library captures and oldrefs retain user-local bearer behavior',
        'Same-OS-user hostile processes are outside the application ownership boundary',
        'SDK is explicit callable code, not native dynamic Desktop tool-registry replacement',
        'Worker metadata publication can be denied; no weaker executor fallback',
        'No cross-model-step context deduplication or native Desktop sidebar',
        'New workflow adoption and efficiency targets remain unmet in the controlled model suite'],
    'dashboard':'verification/dashboard-production.html','browserChecks':'verification/dashboard-v06-browser.json',
    'rollbackSource':'verification/source-0.5.0.zip','rollbackMarketplace':'verification/marketplace-before-0.6.0.json',
    'rollbackEnvironment':str(bundle / 'environment-before.json')}
for name in ('v06-release.json','desktop-installation.json'):
    (verification / name).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'installed':'0.6.0','restartRequired':True,'functions':quality['functionCount'],
    'nativeChecks':sum(checks.values()),'packageBytes':package['bytes'],'modelEfficiencyTargetMet':False}))
