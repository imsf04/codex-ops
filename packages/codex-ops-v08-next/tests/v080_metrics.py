"""Separate paired quality, model calls, native actions and worker measurements."""
from collections import Counter
import json
from pathlib import Path

import task_cost_workflows
from v080_model_tasks import OPPORTUNITIES


def native_actions(row):
    values = row.get('completedItemsByType', {})
    return sum(values.get(key, 0) for key in ('commandExecution','mcpToolCall','fileChange'))


def measured_workers(store):
    path = Path(store)/'mcp-worker-starts.jsonl'
    if not path.exists():
        return {'available':False,'starts':None,'boundary':'MCP child binaries only'}
    try:
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    except (OSError, ValueError):
        return {'available':False,'starts':None,'reason':'Observer log unreadable or incomplete'}
    ready = any(row.get('kind') == 'observer-ready' for row in rows)
    return {'available':ready,'starts':sum(row.get('kind') == 'worker-start' for row in rows) if ready else None,
            'boundary':'MCP child binaries under installed package/bin; native mutation CLI workers not covered'}


def adoption(events, task, automatic=None):
    operations, evidence, selected = Counter(), Counter(), {}
    for event in events:
        item = event.get('params', {}).get('item', {})
        if item.get('type') != 'mcpToolCall' or item.get('tool') != 'ops_workflow':
            continue
        if item.get('id') not in selected or event.get('method') == 'item/completed':
            selected[item.get('id')] = item
    for item in selected.values():
        result = task_cost_workflows._result(item)
        operation = task_cost_workflows.operation(item)
        operations[operation] += 1
        evidence[task_cost_workflows.assess(result)['evidence']] += 1
    eligible = OPPORTUNITIES[task]
    served = [row for row in automatic or [] if row.get('kind') == 'automatic' and row.get('operation') in eligible]
    return {'eligibleTask':True,'eligibleOperations':eligible,'selectedOperations':dict(operations),
            'selectedEligibleWorkflow':any(operations.get(op,0) for op in eligible),
            'evidence':dict(evidence),'automaticEvents':served,
            'automaticallyServed':any(automatic_served(row) for row in served),
            'automaticSaves':sum(row.get('count',0) for row in automatic or []
                                 if row.get('kind')=='automatic' and row.get('operation')=='working_set.save'),
            'firstObservedTool':first_tool(events,eligible),
            'opportunityLabelSource':'Frozen task requirements, not model invocation or success',
            'limits':'Useful evidence is a structural observation, not semantic correctness; oracle labels task success.'}


def automatic_served(row):
    if row.get('evidence') != 'present':
        return False
    return row.get('operation')=='verify' or (row.get('operation')=='working_set' and bool(row.get('reused')))


def first_tool(events, eligible):
    for event in events:
        if event.get('method') != 'item/started':
            continue
        item = event.get('params',{}).get('item',{})
        kind = item.get('type')
        if kind == 'commandExecution':
            return {'tool':'native-command','eligibleWorkflow':False,'basis':'First observed native start, not a semantic opportunity label'}
        if kind == 'mcpToolCall':
            operation = task_cost_workflows.operation(item)
            return {'tool':item.get('tool'),'operation':operation,
                    'eligibleWorkflow':item.get('tool')=='ops_workflow' and operation in eligible,
                    'basis':'First observed native start, not a semantic opportunity label'}
    return None


def total(rows):
    usage = [(r.get('tokens') or {}).get('total', {}) for r in rows]
    inputs = sum(u.get('inputTokens',0) for u in usage)
    cached = sum(u.get('cachedInputTokens',0) for u in usage)
    outer_known = all(r.get('outerCalls') is not None for r in rows)
    worker_known = all(r.get('mcpWorkers',{}).get('available') for r in rows)
    return {'attempts':len(rows),'passed':sum(r.get('outcome',{}).get('passed',False) for r in rows),
            'nativeActions':sum(native_actions(r) for r in rows),
            'outerCalls':sum(sum(r['outerCalls'].values()) for r in rows) if outer_known else None,
            'mcpWorkerStarts':sum(r['mcpWorkers']['starts'] for r in rows) if worker_known else None,
            'inputTokens':inputs,'cachedInputTokens':cached,'uncachedInputTokens':inputs-cached,
            'outputTokens':sum(u.get('outputTokens',0) for u in usage),
            'usageMissing':sum(not bool(r.get('tokens')) for r in rows),
            'selectedEligibleTasks':sum(r.get('adoption',{}).get('selectedEligibleWorkflow',False) for r in rows),
            'automaticallyServedTasks':sum(r.get('adoption',{}).get('automaticallyServed',False) for r in rows)}


def reduction(before, after):
    return 1-after/before if before else None


def comparison(rows, baseline, candidate='v080'):
    keyed = {(r['task'],r['repeat'],r['condition']):r for r in rows}
    keys = sorted({(r['task'],r['repeat']) for r in rows if r['condition'] == baseline})
    paired = [(keyed[(*key,baseline)],keyed[(*key,candidate)]) for key in keys if (*key,candidate) in keyed]
    common = [(a,b) for a,b in paired if a.get('eligibleForComparison') and b.get('eligibleForComparison')
              and a['outcome']['passed'] and b['outcome']['passed']]
    before, after = total([a for a,b in common]), total([b for a,b in common])
    return {'baseline':baseline,'candidate':candidate,'completePairs':len(paired),'commonSuccessfulPairs':len(common),
            'baselineTotals':before,'candidateTotals':after,
            'nativeActionReduction':reduction(before['nativeActions'],after['nativeActions']),
            'inputReduction':reduction(before['inputTokens'],after['inputTokens']),
            'uncachedInputNonIncreasing':after['uncachedInputTokens'] <= before['uncachedInputTokens'] if common else None,
            'baselineSuccessCandidateFailure':sum(a['outcome']['passed'] and not b['outcome']['passed'] for a,b in paired),
            'baselinePasses':sum(a['outcome']['passed'] for a,b in paired),
            'candidatePasses':sum(b['outcome']['passed'] for a,b in paired),
            'qualityNonRegression':sum(b['outcome']['passed'] for a,b in paired) >= sum(a['outcome']['passed'] for a,b in paired)}


def gates(legacy, incremental, complete):
    if not complete:
        return {'status':'INCOMPLETE','releaseGatePassed':False}
    if legacy['commonSuccessfulPairs'] == 0 or incremental['commonSuccessfulPairs'] == 0:
        return {'status':'UNKNOWN','releaseGatePassed':False}
    checks = {'legacyActions25':legacy['nativeActionReduction'] >= .25,
              'legacyInput20':legacy['inputReduction'] >= .20,
              'legacyUncachedNonIncreasing':legacy['uncachedInputNonIncreasing'],
              'legacyQualityNonRegression':legacy['qualityNonRegression'],
              'incrementalQualityNonRegression':incremental['qualityNonRegression'],
              'incrementalUncachedNonIncreasing':incremental['uncachedInputNonIncreasing']}
    return {'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,
            'releaseGatePassed':False,'reason':'Cost gates only; protocol, quality and real native acceptance remain separate.'}


def summarize(rows, planned):
    legacy, incremental = comparison(rows,'v061'), comparison(rows,'v070')
    complete = len(rows) == planned
    gate = gates(legacy,incremental,complete)
    if complete and any(not row.get('eligibleForComparison') for row in rows):
        gate = {'status':'UNKNOWN','releaseGatePassed':False,'reason':'One or more attempts lack complete native/model measurements'}
    return {'complete':complete,'allAttempts':{arm:total([r for r in rows if r['condition']==arm])
                                             for arm in ('v061','v070','v080')},
            'versus061':legacy,'versus070':incremental,'costGate':gate,
            'meaning':'Fresh on-demand trials only. Old frozen v0.7 results remain unchanged. '
                      'Outer calls, native actions and MCP worker starts are distinct levels.'}
