"""Explicit scoped task manifests using the existing observation store and expiry."""
import json
import evidence_index_budget
import working_set_sources
import working_set_current
from workflow_validation import callback, identity, integer, options, require, text


def _sources(args):
    sources = args.get('sources')
    require(isinstance(sources, list) and 1 <= len(sources) <= 8, 'sources requires 1..8 entries')
    return [working_set_sources.request(source) for source in sources]


def _pending(args):
    pending = args.get('pending', [])
    require(isinstance(pending, list) and len(pending) <= 16, 'pending supports at most 16 notes')
    return [text(note, 'pending note', 1000) for note in pending]


def _save(root, args, context, invoke, load, save):
    options(args, ('action', 'sources', 'pending', 'title'))
    sources = _sources(args)
    resolved = [working_set_sources.resolve(root, source, invoke, load) for source in sources]
    require(all(item['state'] in ('current', 'saved-observation') for item in resolved),
            'All sources must be available and current before saving a working set')
    snapshot = {'kind': 'working-set-v1', 'scope': identity(context), 'root': root,
                'title': text(args.get('title', ''), 'title', 1000, empty=True),
                'sources': [working_set_sources.manifest(item) for item in resolved],
                'pending': _pending(args)}
    reference = callback(save, 'save')(snapshot)
    return {'status': 'completed', 'operation': 'working_set', 'effectState': 'none',
            'action': 'save', 'workingSetRef': reference, 'sourceCount': len(sources),
            'nextAction': 'Resume with workingSetRef; each source is reauthorized and file revisions rechecked.'}


def _snapshot(root, args, context, load):
    ref = text(args.get('workingSetRef'), 'workingSetRef', 256)
    value = load(ref)
    require(isinstance(value, dict) and value.get('kind') == 'working-set-v1', 'Not a working set')
    require(value.get('scope') == identity(context), 'Working set belongs to a different session')
    require(value.get('root') == root, 'Working set belongs to a different root')
    return value


def _bounded(item, remaining, save=None):
    result = dict(item)
    result['kind'] = 'working-source'
    result['source'] = working_set_sources.manifest(item)
    if 'currentEvidence' in result:
        return working_set_current.bounded(result, remaining, save)
    if 'value' not in result:
        return result, remaining
    value = result.pop('value', None)
    size = len(json.dumps(value, ensure_ascii=False).encode('utf-8'))
    if size > remaining:
        return {**result, 'contentOmitted': True, 'retrieveRef': item['ref']}, remaining
    return {**result, 'result': value, 'contentOmitted': False}, remaining - size


def _deliver(resolved, budget, save):
    items = []
    for item in resolved:
        bounded, budget = _bounded(item, budget, save)
        items.append(bounded)
    return items


def _resume(root, args, context, invoke, load, save):
    options(args, ('action', 'workingSetRef', 'maxBytes'))
    snapshot = _snapshot(root, args, context, load)
    budget = integer(args, 'maxBytes', 1024, 24576, 12288)
    resolved = [working_set_sources.resolve(root, source, invoke, load)
                for source in snapshot['sources']]
    items = _deliver(resolved, budget, save)
    result = _result(snapshot, items)
    result['continuations'] = [{'operation': 'working_set', 'action': 'resume',
                                'workingSetRef': args['workingSetRef'], 'maxBytes': 24576}]
    return evidence_index_budget.bounded(result, budget)


def _usable(item):
    return item['state'] in ('current', 'saved-observation') and not item.get('contentOmitted')


def _result(snapshot, items):
    usable = all(_usable(item) for item in items)
    return {'kind': 'evidence-packet', 'schemaVersion': 1,
            'status': 'completed' if usable else 'partial',
            'operation': 'working_set', 'effectState': 'none', 'action': 'resume',
            'evidenceState': 'collected' if usable else 'partial',
            'coverage': {'sourceScanComplete': usable, 'selectionComplete': usable},
            'title': snapshot['title'], 'items': items, 'pending': snapshot['pending'],
            'pendingMeaning': 'Caller-provided notes, not independently verified facts',
            'contextRetentionAssumed': False,
            'sourceCompleteness': 'Saved observations; file freshness checked only for sources with path/revision',
            'nextAction': 'Use delivered currentEvidence for changed files; old snapshots remain stale. Retrieve omitted currentEvidenceRef when provided; read only missing ranges or unavailable sources.'}


def run(root, args, context, invoke=None, load=None, save=None):
    identity(context)
    loader = callback(load, 'load')
    action = args.get('action')
    if action == 'save':
        return _save(root, args, context, invoke, loader, save)
    require(action == 'resume', 'working_set action must be save or resume')
    return _resume(root, args, context, invoke, loader, save)
