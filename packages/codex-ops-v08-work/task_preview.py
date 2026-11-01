"""Bounded plan receipts retain native execution and explicit omitted-step counts."""
from reducers import clip, encode
import task_api


def summary(value):
    complete = task_api.summary(value)
    steps = complete.pop('steps')
    roots = complete.pop('roots')
    selected = [{**row, 'path': clip(row['path'], 240)} for row in steps[:8]]
    return {**complete, 'steps': selected, 'omittedSteps': len(steps) - len(selected),
            'roots': [clip(name, 240) for name in roots[:8]], 'omittedRoots': max(0, len(roots) - 8),
            'detailsPath': '/steps', 'nextAction': 'Inspect omitted steps and exact paths in the saved plan before execution.'}


def capture(store, value):
    receipt = store.capture(value, scope='task-plan', force=True)
    if receipt.get('kind') != 'reference':
        return receipt
    receipt.update(purpose='task-plan', preview=summary(value),
                   nativeExecution=task_api.command('apply', reference=receipt['ref']))
    return receipt
