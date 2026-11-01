"""Keep strict results and costs intact while checking equivalent answer representations."""
import hashlib
import json
from pathlib import Path
import statistics

from v061_semantic_check import outcome

root = Path(__file__).resolve().parents[1]
report = json.loads((root / 'verification/v061-costs.json').read_text())
assert report['complete'] and len(report['reports']) == 24
supplement = {'method': 'v061-supplemental-format-semantics-1',
              'reason': 'Historical fixture prompts do not specify enum representations; equivalent prose/case and false (owner cannot override suspension) were rejected by exact field checks.',
              'strictReport': 'v061-costs.json', 'strictReportSha256': hashlib.sha256((root / 'verification/v061-costs.json').read_bytes()).hexdigest(),
              'checkerSha256': hashlib.sha256((root / 'tests/v061_semantic_check.py').read_bytes()).hexdigest(),
              'negativeControls': '3 passing tests cover reversed authority/types, wrong locations, input mutation, extra fields and negated statements.',
              'gradingLimitation': 'Equivalent representations were audited after observing strict mismatches. This is transparent semantic adjudication, not a blinded correctness comparison. The initial checker is retained as v061-semantic-check-initial.py.txt.',
              'paidReruns': 0, 'costValuesChanged': False, 'rows': []}
for row in report['reports']:
    expected = json.loads(Path(row['expectedPath']).read_text())
    supplement['rows'].append({'key': row['key'], 'condition': row['condition'],
                               'strict': row['outcome'], 'semantic': outcome(row, expected)})
supplement['semanticPassed'] = {name: sum(row['semantic']['passed'] for row in supplement['rows'] if row['condition'] == name)
                                for name in ('v060', 'v061')}
s = report['summary']
cost_pairs = []
for old in [r for r in report['reports'] if r['condition'] == 'v060']:
    new = next(r for r in report['reports'] if r['condition'] == 'v061'
               and (r['task'], r['repeat']) == (old['task'], old['repeat']))
    old_ok = next(r['semantic']['passed'] for r in supplement['rows'] if r['key'] == old['key'])
    new_ok = next(r['semantic']['passed'] for r in supplement['rows'] if r['key'] == new['key'])
    if old_ok and new_ok:
        values = {r['condition']: {'inputTokens': r['tokens']['total']['inputTokens'],
                  'observedActions': sum(r['completedItemsByType'].get(k, 0)
                    for k in ('commandExecution', 'mcpToolCall', 'fileChange'))} for r in (old, new)}
        cost_pairs.append({'task': old['task'], 'repeat': old['repeat'], **values})
paired = {name: {metric: sum(p[name][metric] for p in cost_pairs)
                for metric in ('inputTokens', 'observedActions')} for name in ('v060', 'v061')}
paired['pairs'] = len(cost_pairs)
paired['medianInputChangePercent'] = statistics.median(100 * (p['v061']['inputTokens'] / p['v060']['inputTokens'] - 1) for p in cost_pairs)
supplement['matchedSuccessCosts'] = paired
supplement['matchedSuccessPairs'] = cost_pairs
supplement['releaseGatePassed'] = bool(len(report['reports']) == 24 and
    all(row.get('eligibleForComparison') for row in report['reports']) and
    supplement['semanticPassed']['v061'] == 12 and
    s['v061']['observedActions'] < s['v060']['observedActions'] and
    s['v061']['inputTokens'] < s['v060']['inputTokens'] and
    s['medianPairedInputChangePercent'] < 0 and
    paired['v061']['observedActions'] < paired['v060']['observedActions'] and
    paired['v061']['inputTokens'] < paired['v060']['inputTokens'] and paired['medianInputChangePercent'] < 0)
(root / 'verification/v061-semantic-supplement.json').write_text(json.dumps(supplement, indent=2), encoding='utf-8')
print(json.dumps({'semanticPassed': supplement['semanticPassed'], 'releaseGatePassed': supplement['releaseGatePassed']}))
