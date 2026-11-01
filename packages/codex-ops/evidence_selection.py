"""Keep source diversity and compact, explicit cursor coverage."""
from collections import defaultdict, deque

SUMMARY = ('status', 'complete', 'pageComplete', 'scanComplete', 'truncated', 'truncatedBy',
           'nextOffset', 'nextIndex', 'pending', 'failed', 'omitted', 'skippedFiles', 'skipReasons', 'error')


def coverage(value):
    return {key: value[key] for key in SUMMARY if key in value}


def context(value):
    result = coverage(value)
    pages = []
    for item in value.get('items', []):
        if item.get('complete') is False or item.get('error'):
            pages.append({'path': item.get('path'), **coverage(item)})
    if pages:
        result['pages'] = pages
    return result


def prioritized(rows, anchors):
    groups = defaultdict(list)
    for row in rows:
        groups[row['source']['path']].append(row)
    queues = [deque(sorted(group, key=lambda row: _rank(row, anchors))) for group in groups.values()]
    result = []
    while any(queues):
        for group in queues:
            if group:
                result.append(group.popleft())
    return result


def _rank(row, anchors):
    content = row['text']
    return (not bool(content.strip()), not any(anchor in content for anchor in anchors), row['location']['line'])


def continuations(stages):
    chosen = {}
    for stage in stages:
        chosen[stage['args']['path']] = {'tool': 'ops_workflow', 'operation': 'locate', 'args': dict(stage['args'])}
    return list(chosen.values())
