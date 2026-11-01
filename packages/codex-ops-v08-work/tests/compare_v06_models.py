"""Compare every paid attempt while withholding invalid efficiency claims."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics

from compare_model_benchmark import reduction, usage


def work_items(row):
    counts = row.get('completedItemsByType', {})
    return sum(counts.get(key, 0) for key in ('commandExecution', 'mcpToolCall', 'fileChange'))


def condition_summary(rows):
    valid = [row for row in rows if row.get('eligibleForComparison')]
    known = [usage(row) for row in rows]
    tools = Counter()
    for row in rows:
        tools.update(row.get('completedMcpTools', {}))
    return {'attempts': len(rows), 'passed': sum(row['outcome']['passed'] for row in rows),
            'validEnvironmentAttempts': len(valid), 'incomplete': sum(row.get('turnStatus') != 'completed' for row in rows),
            'knownTotalTokens': sum(row.get('totalTokens', 0) for row in known),
            'knownInputTokens': sum(row.get('inputTokens', 0) for row in known),
            'knownCachedInputTokens': sum(row.get('cachedInputTokens', 0) for row in known),
            'missingUsageAttempts': sum(not row.get('tokens') for row in rows),
            'medianWallSecondsAllAttempts': statistics.median(row['wallSeconds'] for row in rows) if rows else None,
            'completedMcpTools': dict(tools)}


def pair(left, right):
    same_model = left.get('model') == right.get('model') and bool(left.get('model'))
    same_layout = left.get('workspaceLayout') == right.get('workspaceLayout') and bool(left.get('workspaceLayout'))
    environment = same_model and same_layout and left.get('eligibleForComparison') and right.get('eligibleForComparison')
    successful = left['outcome']['passed'] and right['outcome']['passed']
    output = {'task': left['task'], 'repeat': left['repeat'], 'leftKey': left['key'], 'rightKey': right['key'],
              'leftPassed': left['outcome']['passed'], 'rightPassed': right['outcome']['passed'],
              'sameModel': same_model, 'sameLayout': same_layout, 'environmentValid': bool(environment),
              'comparableSuccessfulPair': bool(environment and successful),
              'leftUsage': usage(left), 'rightUsage': usage(right),
              'leftWallSeconds': left['wallSeconds'], 'rightWallSeconds': right['wallSeconds'],
              'leftWorkItems': work_items(left), 'rightWorkItems': work_items(right),
              'startTimeSeparationSeconds': abs(left.get('startedAt', 0) - right.get('startedAt', 0))}
    if output['comparableSuccessfulPair']:
        for key in ('totalTokens', 'inputTokens', 'inputMinusCachedTokens'):
            a, b = output['leftUsage'].get(key), output['rightUsage'].get(key)
            output[key + 'ReductionPercent'] = reduction(a, b) if a is not None and b is not None else None
        output['wallTimeReductionPercent'] = reduction(left['wallSeconds'], right['wallSeconds'])
        output['workItemReductionPercent'] = reduction(work_items(left), work_items(right))
    return output


def comparison(rows, left_name, right_name):
    left = {(row['task'], row['repeat']): row for row in rows if row['condition'] == left_name}
    right = {(row['task'], row['repeat']): row for row in rows if row['condition'] == right_name}
    pairs = [pair(left[key], right[key]) for key in sorted(left.keys() & right.keys())]
    metrics = ('totalTokensReductionPercent', 'inputTokensReductionPercent',
               'inputMinusCachedTokensReductionPercent', 'wallTimeReductionPercent', 'workItemReductionPercent')
    medians = {}
    for metric in metrics:
        values = [row[metric] for row in pairs if row.get(metric) is not None]
        medians[metric] = statistics.median(values) if values else None
    return {'left': left_name, 'right': right_name, 'pairedAttempts': len(pairs),
            'comparableSuccessfulPairs': sum(row['comparableSuccessfulPair'] for row in pairs),
            'leftOnly': len(left.keys() - right.keys()), 'rightOnly': len(right.keys() - left.keys()),
            'newFailures': [row['rightKey'] for row in pairs if row['leftPassed'] and not row['rightPassed']],
            'newSuccesses': [row['rightKey'] for row in pairs if not row['leftPassed'] and row['rightPassed']],
            'medianPairedReductions': medians, 'pairs': pairs}


def _corrected(row, correction):
    value = {**row, 'originalOutcome': row['outcome'], 'outcome': correction['correctedOutcome']}
    if correction.get('environmentRecovery'):
        value['eligibleForComparison'] = bool(row.get('treatmentValid') and not row.get('environmentBlocked')
            and row.get('tokens') and row.get('turnStatus') == 'completed'
            and not correction['correctedOutcome'].get('evaluationBlocked'))
    return value


def summarize(suite, corrections=None):
    corrected = {row['key']: row for row in (corrections or {}).get('changes', [])}
    rows = [_corrected(row, corrected[row['key']])
            if row['key'] in corrected else row for row in suite['reports']]
    comparisons = [comparison(rows, a, b) for a, b in (('native', 'v05'), ('native', 'v06'), ('v05', 'v06'))]
    return {'version': '0.6.0', 'complete': suite['complete'], 'plannedTrials': len(suite['schedule']),
            'completedTrials': len(rows), 'model': suite['model'],
            'outcomeMetric': 'Frozen structured-output/file-effect conformance; unsupported synonymous wording can fail despite correct reasoning',
            'environmentAttempts': suite.get('environmentAttempts', []),
            'actualExecutionOrder': [row['key'] for row in sorted(rows, key=lambda row: row.get('startedAt', 0))],
            'executionPhases': 'Native/v05 ran in an interleaved first block; v06 ran later after candidate freeze. Planned three-condition order was not fully executed interleaved.',
            'conditions': {name: condition_summary([row for row in rows if row['condition'] == name])
                           for name in ('native', 'v05', 'v06')},
            'comparisons': comparisons, 'oracleCorrections': corrections,
            'limitations': [*suite['limitations'],
                'Efficiency reductions cover successful environment-valid pairs only; all outcomes and failures remain visible',
                'Work-item counts cover completed native command/MCP/file-change events; they are not total nested JS tool invocation counts',
                'Total/input token metrics include cached repeated context; input-minus-cached is descriptive, not a bill',
                'Per-task repeated results are correlated; no claim of statistical significance',
                'v06 ran in a later block; observed efficiency differences do not isolate treatment from time/cache/system-load effects',
                'Enabled groups eagerly inject the entire skill on every fixture; daily on-demand skill loading and actual PostToolUse hook execution are not reproduced',
                'This does not benchmark DeepSeek Harness or establish cross-harness superiority']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--corrections', type=Path)
    args = parser.parse_args()
    correction_path = args.corrections or args.suite.with_name('model-v06-oracle-corrections.json')
    corrections = json.loads(correction_path.read_text(encoding='utf-8')) if correction_path.exists() else None
    recovery_path = args.suite.with_name('model-v06-document-oracle-recovery.json')
    if recovery_path.exists():
        recovery = json.loads(recovery_path.read_text(encoding='utf-8'))
        corrections = corrections or {'changes': []}
        corrections['changes'].append({**recovery, 'environmentRecovery': True})
    result = summarize(json.loads(args.suite.read_text(encoding='utf-8')), corrections)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'complete': result['complete'], 'completedTrials': result['completedTrials'],
                      'conditions': result['conditions']}))


if __name__ == '__main__':
    main()
