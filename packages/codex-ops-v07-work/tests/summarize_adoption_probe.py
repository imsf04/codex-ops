"""Account for every routing probe, including failed attempts and retrieval overhead."""
from collections import Counter
import json
from pathlib import Path
import statistics

root = Path(__file__).resolve().parents[1]
report = json.loads((root / 'verification/v06-adoption-probe.json').read_text())
assert report['complete'] and len(report['reports']) == 12
summary = {'experiment': report['experiment'], 'model': report['model'], 'trials': 12,
           'conditions': {}, 'pairs': [], 'limitations': report['limitations'] + [
               'Background candidate unit tests overlapped some trials; elapsed time is descriptive, not a causal speed comparison.',
               'Instructions differ in both routing examples and length; token differences cannot be attributed solely to workflow use.',
               'The candidate diagnostic/catalogue code fixes were not part of these model trials.']}
for condition in ('original', 'routed'):
    rows = [row for row in report['reports'] if row['condition'] == condition]
    tools, operations, failures = Counter(), Counter(), []
    for row in rows:
        tools.update(row.get('completedMcpTools', {}))
        for line in Path(row['eventsPath']).read_text(encoding='utf-8').splitlines():
            event = json.loads(line)
            item = event.get('params', {}).get('item', {})
            if event.get('method') != 'item/completed' or item.get('tool') != 'ops_workflow':
                continue
            operations[item['arguments']['operation']] += 1
            result = item.get('result') or {}
            if result.get('isError'):
                failures.append({'key': row['key'], 'error': result})
    summary['conditions'][condition] = {
        'trials': len(rows), 'passed': sum(row['outcome']['passed'] for row in rows),
        'workflowAdoptedTasks': sum(any(name.endswith('.ops_workflow') and count > 0
                                      for name, count in row.get('completedMcpTools', {}).items()) for row in rows),
        'tools': dict(tools), 'workflowOperations': dict(operations), 'mcpTransportErrors': failures,
        'nativeCommands': sum(row.get('completedItemsByType', {}).get('commandExecution', 0) for row in rows),
        'inputTokens': sum(row['tokens']['total']['inputTokens'] for row in rows),
        'cachedInputTokens': sum(row['tokens']['total']['cachedInputTokens'] for row in rows),
        'wallSecondsSum': round(sum(row['wallSeconds'] for row in rows), 3),
        'instructionsBytes': len(report['instructions'][condition].encode())}
for original in [row for row in report['reports'] if row['condition'] == 'original']:
    routed = next(row for row in report['reports'] if row['condition'] == 'routed'
                  and row['task'] == original['task'] and row['repeat'] == original['repeat'])
    summary['pairs'].append({'task': original['task'], 'repeat': original['repeat'],
                            'bothPassed': original['outcome']['passed'] and routed['outcome']['passed'],
                            'inputChangePercent': round(100 * (routed['tokens']['total']['inputTokens'] /
                                                               original['tokens']['total']['inputTokens'] - 1), 2),
                            'wallChangePercent': round(100 * (routed['wallSeconds'] / original['wallSeconds'] - 1), 2)})
summary['medianPairedInputChangePercent'] = statistics.median(row['inputChangePercent'] for row in summary['pairs'])
destination = root / 'verification/v06-adoption-summary.json'
destination.write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in summary.items() if key not in ('pairs', 'limitations')}, indent=2))
