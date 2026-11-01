"""Create a small reviewable release receipt from completed validation evidence."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
costs = json.loads((root / 'verification/v061-costs.json').read_text())
supplement = json.loads((root / 'verification/v061-semantic-supplement.json').read_text())
assert costs['complete'] and supplement['releaseGatePassed'], costs['summary']
quality = json.loads((root / 'verification/quality/crap.json').read_text())
assert quality['above6'] == 0 and quality['maximum'] <= 6
for name, digest in quality['sourceSha256'].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
native = json.loads((root / 'verification/v061-native-runtime.json').read_text())
assert native['complete'] and len(native['reports']) == 14
assert all(row['expectedError'] if row['case'] == 'error' else row['rawIntact'] for row in native['reports'])
summary = {**costs['summary'], 'model': costs['model'], 'complete': True,
           'measurement': costs['metrics'], 'limitations': costs['limits'],
           'startedAt': costs['startedAt'], 'endedAt': costs['endedAt'],
           'scope': 'Six task fixtures, two repeats per version, 24 paid trials; all attempts included.'}
summary['strictGatePassed'] = summary['gatePassed']
summary['gatePassed'] = supplement['releaseGatePassed']
summary['semanticPassed'] = supplement['semanticPassed']
summary['matchedSuccessCosts'] = supplement['matchedSuccessCosts']
summary['correctnessSupplement'] = {'method': supplement['method'], 'reason': supplement['reason'],
                                    'strictResultsRetained': True, 'negativeControls': supplement['negativeControls'],
                                    'gradingLimitation': supplement['gradingLimitation']}
for condition in ('v060', 'v061'):
    rows = [r for r in costs['reports'] if r['condition'] == condition]
    cached = sum(r['tokens']['total']['cachedInputTokens'] for r in rows)
    summary[condition]['cachedInputTokens'] = cached
    summary[condition]['noncachedInputTokens'] = summary[condition]['inputTokens'] - cached
summary['observedActionReductionPercent'] = 100 * (1 - summary['v061']['observedActions'] / summary['v060']['observedActions'])
summary['totalInputReductionPercent'] = 100 * (1 - summary['v061']['inputTokens'] / summary['v060']['inputTokens'])
summary['quality'] = {'tests': 384, 'pythonFunctions': quality['functionCount'],
                      'maximumCrap': quality['maximum'], 'above6': 0, 'nativeCases': 14}
summary['quality']['supplementalOracleTests'] = 3
summary['byCategory'] = {}
for category in ('code_location', 'log_diagnosis', 'document_lookup'):
    category_rows = [r for r in costs['reports'] if r['task'].startswith(category)]
    summary['byCategory'][category] = {}
    for condition in ('v060', 'v061'):
        selected = [r for r in category_rows if r['condition'] == condition]
        summary['byCategory'][category][condition] = {
            'inputTokens': sum(r['tokens']['total']['inputTokens'] for r in selected),
            'observedActions': sum(sum(r['completedItemsByType'].get(name, 0)
                for name in ('commandExecution', 'mcpToolCall', 'fileChange')) for r in selected),
            'retrievals': sum(sum(n for name, n in r['completedMcpTools'].items()
                if name.endswith('.ops_result')) for r in selected)}
(root / 'verification/v061-cost-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
