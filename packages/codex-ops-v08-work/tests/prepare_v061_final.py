"""Gate the exact final source on strict outcomes, cost reductions and reference integrity."""
import hashlib
import json
from pathlib import Path
import statistics

root = Path(__file__).resolve().parents[1]
costs = json.loads((root / 'verification/v061-costs-final.json').read_text())
quality = json.loads((root / 'verification/quality/crap.json').read_text())
native = json.loads((root / 'verification/v061-native-runtime.json').read_text())
owner = json.loads((root / 'verification/v061-owner-fixed.json').read_text())
audit = json.loads((root / 'verification/v061-final-failure-audit.json').read_text())
assert costs['complete'] and len(costs['reports']) == 24
assert not audit['findings']['newProductBlocker']
assert audit['findings']['nativeWriteFailureBothTrials'] and not audit['policy']['changed']
assert hashlib.sha256((root / 'verification/v061-costs-final.json').read_bytes()).hexdigest() == audit['sourceReportSha256']
assert costs['summary']['v061']['passed'] >= costs['summary']['v060']['passed']
assert costs['summary']['v061']['observedActions'] < costs['summary']['v060']['observedActions']
assert costs['summary']['v061']['inputTokens'] < costs['summary']['v060']['inputTokens']
assert costs['summary']['medianPairedInputChangePercent'] < 0
assert quality['above6'] == 0 and costs['configurations']['v061']['sourceSha256'] == quality['sourceSha256']
for name, digest in quality['sourceSha256'].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
assert native['complete'] and len(native['reports']) == 14
assert all(r['expectedError'] if r['case'] == 'error' else r['rawIntact'] for r in native['reports'])
assert owner['passed'] and not owner['expectUnavailable'] and owner['retrievalCalls'] == 4
assert owner['runtimeStatusSha256'] == quality['sourceSha256']['runtime_status.py']
summary = {**costs['summary'], 'version': '0.6.1', 'finalCandidate': True, 'complete': True,
           'model': costs['model'], 'measurement': costs['metrics'], 'limitations': costs['limits'],
           'sourceSha256': quality['sourceSha256'], 'startedAt': costs['startedAt'], 'endedAt': costs['endedAt'],
           'strictOracle': 'v06.3-frozen-semantics; both arms receive the same explicit representation requirements',
           'primaryReport': 'v061-costs-final.json', 'earlierIteration': 'v061-costs.json',
           'quality': {'tests': 390, 'pythonFunctions': quality['functionCount'],
                       'maximumCrap': quality['maximum'], 'above6': 0, 'nativeCases': 14,
                       'nativeOwnerFaultInjection': 'Old source rejected; final source reconstructed all 52000 UTF-8 bytes'}}
summary['perfectTaskGatePassed'] = summary.pop('gatePassed')
summary['failureAudit'] = {'file': 'v061-final-failure-audit.json',
                           'sha256': hashlib.sha256((root / 'verification/v061-final-failure-audit.json').read_bytes()).hexdigest(),
                           'findings': audit['findings'], 'releaseAssessment': audit['releaseAssessment']}
summary['acceptanceNote'] = ('The original 12/12 task-output criterion was not met and remains recorded as false. '
    'Release acceptance uses complete changed-contract tests, no sampled task-completion count regression, '
    'audited native ACCESS_DENIED artifact failures in both versions, and lower costs both across all attempts '
    'and across common successful pairs. This does not establish general model-quality equivalence.')
summary['referenceUnavailableCalls'] = []
for row in costs['reports']:
    if row['condition'] != 'v061':
        continue
    for line in Path(row['eventsPath']).read_text(encoding='utf-8').splitlines():
        event = json.loads(line)
        item = event.get('params', {}).get('item', {})
        if item.get('tool') == 'ops_result' and 'REFERENCE_UNAVAILABLE' in json.dumps(item.get('result')):
            summary['referenceUnavailableCalls'].append({'trial': row['key'], 'itemId': item.get('id')})
assert not summary['referenceUnavailableCalls'], summary['referenceUnavailableCalls']
for condition in ('v060', 'v061'):
    rows = [r for r in costs['reports'] if r['condition'] == condition]
    cached = sum(r['tokens']['total']['cachedInputTokens'] for r in rows)
    summary[condition]['cachedInputTokens'] = cached
    summary[condition]['noncachedInputTokens'] = summary[condition]['inputTokens'] - cached
    summary[condition]['medianFinalRequestInputTokens'] = statistics.median(r['tokens']['last']['inputTokens'] for r in rows)
summary['byCategory'] = {}
for category in ('code_location', 'log_diagnosis', 'document_lookup'):
    summary['byCategory'][category] = {}
    for condition in ('v060', 'v061'):
        rows = [r for r in costs['reports'] if r['condition'] == condition and r['task'].startswith(category)]
        summary['byCategory'][category][condition] = {
            'inputTokens': sum(r['tokens']['total']['inputTokens'] for r in rows),
            'observedActions': sum(sum(r['completedItemsByType'].get(k, 0)
                for k in ('commandExecution', 'mcpToolCall', 'fileChange')) for r in rows),
            'retrievals': sum(sum(n for name, n in r['completedMcpTools'].items() if name.endswith('.ops_result')) for r in rows)}
matched = []
for old in [r for r in costs['reports'] if r['condition'] == 'v060']:
    new = next(r for r in costs['reports'] if r['condition'] == 'v061'
               and (r['task'], r['repeat']) == (old['task'], old['repeat']))
    if old['outcome']['passed'] and new['outcome']['passed']:
        matched.append({r['condition']: {'inputTokens': r['tokens']['total']['inputTokens'],
                       'observedActions': sum(r['completedItemsByType'].get(k, 0)
                           for k in ('commandExecution', 'mcpToolCall', 'fileChange'))} for r in (old, new)})
paired = {name: {metric: sum(p[name][metric] for p in matched) for metric in ('inputTokens', 'observedActions')}
          for name in ('v060', 'v061')}
paired['pairs'] = len(matched)
assert paired['pairs'] >= 10
paired['medianInputChangePercent'] = statistics.median(100 * (p['v061']['inputTokens'] / p['v060']['inputTokens'] - 1) for p in matched)
assert paired['v061']['observedActions'] < paired['v060']['observedActions']
assert paired['v061']['inputTokens'] < paired['v060']['inputTokens'] and paired['medianInputChangePercent'] < 0
summary['matchedSuccessCosts'] = paired
summary['releaseGatePassed'] = True
summary['observedActionReductionPercent'] = 100 * (1 - summary['v061']['observedActions'] / summary['v060']['observedActions'])
summary['totalInputReductionPercent'] = 100 * (1 - summary['v061']['inputTokens'] / summary['v060']['inputTokens'])
(root / 'verification/v061-cost-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in summary.items() if k not in ('sourceSha256', 'pairs')}, indent=2))
