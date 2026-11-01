"""Account actual usage and actions separately; never infer savings from bytes."""
from collections import Counter
from pathlib import Path
import re
import task_cost_records as records_api
import task_cost_workflows
import task_cost_cohorts
import cost_events

TOKEN_KEYS = ('input_tokens', 'cached_input_tokens', 'output_tokens', 'total_tokens')
ACTION_TYPES = frozenset(('CommandExecution', 'McpToolCall', 'FileChange'))
CHAT = re.compile(r'chat:([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})\Z')


def report(context=None, sessions_root=None, *, since=None, until=None, turn_id=None, origin='production'):
    match = CHAT.fullmatch(context or '')
    if match is None:
        return _unavailable('Native chat identity unavailable; no runtime-ID inference')
    root = Path(sessions_root) if sessions_root else Path.home() / '.codex/sessions'
    try:
        result = _report_files(root, match.group(1).lower(), since=since, until=until, turn_id=turn_id)
        result['runtimeMeasurements'] = cost_events.snapshot(context, since=task_cost_cohorts.boundary(since),
                                                            until=task_cost_cohorts.boundary(until), origin=origin)
        return result
    except (OSError, ValueError) as exc:
        return _unavailable(str(exc))


def _unavailable(reason):
    return {'available': False, 'reason': reason, 'measurement': 'No estimated token savings'}


def _report_files(root, session, **cohort):
    paths = list(root.glob('**/*' + session + '.jsonl'))
    if not paths:
        return _unavailable('No local rollout for the native chat')
    records = records_api.read(paths)
    selected = [r for r in records if records_api.identity(r) == session]
    result = summarize(selected, cohort=cohort)
    result.update(available=True, session='chat:' + session, files=len(paths))
    result['cohort'] = 'Current chat only; plugin development/validation is not automatically reclassified as daily work'
    return result


def _usage(value):
    result = {key: value.get(key, 0) for key in TOKEN_KEYS}
    if not all(_valid_count(number) for number in result.values()):
        raise ValueError('Usage counts must be nonnegative integers')
    if result['cached_input_tokens'] > result['input_tokens']:
        raise ValueError('Cached input exceeds total input')
    result['total_tokens'] = value.get('total_tokens', result['input_tokens'] + result['output_tokens'])
    return result


def _valid_count(number):
    return type(number) is int and number >= 0


def _native(record):
    payload = record.get('payload', {})
    if payload.get('type') != 'item_completed':
        return None
    item = payload.get('item', {})
    return item if item.get('type') in ACTION_TYPES else None


def _outer(record):
    value = record.get('payload', {})
    if value.get('type') in ('custom_tool_call', 'function_call'):
        return value
    return None


def _unique(counter, seen, key, name):
    if key is None or key in seen:
        return
    seen.add(key)
    counter[name] += 1


def _actions(records):
    counts, outer, seen_native, seen_outer = Counter(), Counter(), set(), set()
    for record in records:
        item = _native(record)
        if item is not None:
            _unique(counts, seen_native, item.get('id'), item['type'])
        item = _outer(record)
        if item is not None:
            _unique(outer, seen_outer, item.get('call_id'), item.get('name', 'unknown'))
    return dict(counts), dict(outer)


def _authoritative(record):
    return record.get('type') == 'token_usage_record'


def _eligible(records, excluded):
    ancestry = records_api.parents(records)
    return [r for r in records if records_api.root(records_api.identity(r), ancestry) not in excluded]


def _usage_row(record, authoritative_sessions):
    payload = record.get('payload', {})
    session = records_api.identity(record)
    if _authoritative(record):
        return payload.get('response_id'), payload.get('usage'), 'authoritative'
    if session in authoritative_sessions or payload.get('type') != 'token_count':
        return None, None, None
    info = payload.get('info') or {}
    signature = str(info.get('total_token_usage'))
    return (session, signature), info.get('last_token_usage'), 'fallback-last-request'


def _tokens(records):
    sessions = {records_api.identity(r) for r in records if _authoritative(r)}
    totals, sources, seen = Counter(), Counter(), set()
    for record in records:
        key, usage, source = _usage_row(record, sessions)
        if not _new_usage(key, usage, seen):
            continue
        seen.add(key)
        totals.update(_usage(usage))
        sources[source] += 1
    return dict(totals), dict(sources)


def _new_usage(key, usage, seen):
    return key is not None and usage is not None and key not in seen


def summarize(records, excluded_roots=(), cohort=None):
    selected = _eligible(records, set(excluded_roots))
    selected, selection = task_cost_cohorts.select(selected, **(cohort or {}))
    tokens, sources = _tokens(selected)
    native, outer = _actions(selected)
    unassigned = sum(records_api.identity(r) is None for r in selected)
    return {'status': 'completed', 'effectState': 'none', 'operation': 'cost',
            'tokens': tokens, 'usageSources': sources,
            'uncachedInputTokens': tokens.get('input_tokens', 0) - tokens.get('cached_input_tokens', 0),
            'nativeActions': native, 'nativeActionCount': sum(native.values()), 'outerCalls': outer,
            'workflowUsage': task_cost_workflows.summarize(selected),
            'selection': selection,
            'attribution': {'unassignedRecords': unassigned, 'adaptiveEligible': unassigned == 0},
            'excludedRoots': list(excluded_roots),
            'measurement': 'Actual request usage, not savings. Native actions and outer calls are separate.',
            'limitations': ['Fallback counts observed last requests only; missing requests are not reconstructed.',
                            'Any authoritative usage in a session suppresses token_count fallback for that session.',
                            'No counterfactual or price model; no claimed token or monetary savings.']}
