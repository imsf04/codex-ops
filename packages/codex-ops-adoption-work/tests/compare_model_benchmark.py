"""Join completed controlled-task reports without hiding failed or negative outcomes."""
import argparse
import json
from pathlib import Path


def usage(row):
    total = (row.get('tokens') or {}).get('total', {})
    inputs, cached = total.get('inputTokens'), total.get('cachedInputTokens')
    return {**total, 'inputMinusCachedTokens': inputs - cached if inputs is not None and cached is not None else None}


def reduction(before, after):
    return round(100 * (before - after) / before, 2) if before else None


def compare(baseline, enabled):
    before = {row['task']: row for row in baseline['reports']}
    after = {row['task']: row for row in enabled['reports']}
    rows = []
    for task in baseline['selectedTasks']:
        left, right = before.get(task), after.get(task)
        if left is None or right is None:
            rows.append({'task': task, 'paired': False})
            continue
        same_model = left.get('model') == right.get('model') and left.get('model') is not None
        successful = left['outcome']['passed'] and right['outcome']['passed']
        valid = bool(same_model and left['eligibleForComparison'] and right['eligibleForComparison'])
        same_layout = left.get('workspaceLayout') == right.get('workspaceLayout') and left.get('workspaceLayout') is not None
        left_usage, right_usage = usage(left), usage(right)
        row = {'task': task, 'paired': True, 'baselinePassed': left['outcome']['passed'],
               'enabledPassed': right['outcome']['passed'], 'sameModel': same_model,
               'environmentAndTreatmentValid': valid, 'workspaceLayoutsComparable': same_layout,
               'comparableSuccessfulTask': bool(valid and same_layout and successful),
               'baselineUsage': left_usage, 'enabledUsage': right_usage,
               'baselineWallSeconds': left['wallSeconds'], 'enabledWallSeconds': right['wallSeconds'],
               'baselineCompletedItems': left['completedItemsByType'], 'enabledCompletedItems': right['completedItemsByType']}
        if row['comparableSuccessfulTask']:
            row['totalTokenReductionPercent'] = reduction(left_usage.get('totalTokens'), right_usage.get('totalTokens'))
            row['wallTimeReductionPercent'] = reduction(left['wallSeconds'], right['wallSeconds'])
        rows.append(row)
    return {'type': 'five-controlled-tasks-paired-comparison', 'baselineComplete': baseline['complete'],
            'enabledComplete': enabled['complete'], 'baselineSuccesses': sum(row['outcome']['passed'] for row in before.values()),
            'enabledSuccesses': sum(row['outcome']['passed'] for row in after.values()), 'tasks': rows,
            'limitations': ['One attempt per task/condition; no statistical confidence or broad quality claim.',
                            'Only successful paired tasks receive token/time reduction percentages.',
                            'Input tokens include cached input; inputMinusCachedTokens is a descriptive difference, not billing.',
                            'Run order, concurrent system load and model nondeterminism affect measured time and tokens.',
                            'Changed temporary-directory permission layouts are not used for token/time savings percentages.',
                            'Enabled includes both the runtime bridge and six MCP tools; this does not isolate either component.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--enabled', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare(json.loads(args.baseline.read_text(encoding='utf-8')), json.loads(args.enabled.read_text(encoding='utf-8')))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'baselineSuccesses': result['baselineSuccesses'], 'enabledSuccesses': result['enabledSuccesses'],
                      'pairedTasks': len(result['tasks']), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
