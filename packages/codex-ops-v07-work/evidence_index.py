"""Read-only lexical search across currently authorized saved observations."""
import evidence_index_query
import evidence_index_rows
import evidence_index_budget
from store import ReferenceUnavailable
from workflow_validation import callback, coverage, identity, integer, options, require, text


def _references(args):
    refs = args.get('refs')
    require(isinstance(refs, list) and 1 <= len(refs) <= 8, 'refs requires 1..8 saved references')
    refs = [text(ref, 'reference', 256) for ref in refs]
    require(len(set(refs)) == len(refs), 'Duplicate references are not supported')
    return refs


def _source(ref, load):
    try:
        value = load(ref)
    except (ValueError, OSError, KeyError, ReferenceUnavailable) as exc:
        return [], {'ref': ref, 'status': 'unavailable', 'reason': str(exc)}
    rows, scan = evidence_index_rows.flatten(value)
    for row in rows:
        row['ref'] = ref
        row.update(kind='reference-excerpt', source={'ref': ref, 'pointer': row['pointer']},
                   location={'offset': row['offset']})
    source = coverage(value) if isinstance(value, dict) else {}
    return rows, {'ref': ref, 'status': 'available', **scan, 'sourceCoverage': source}


def _collect(refs, load):
    rows, sources = [], []
    for ref in refs:
        found, source = _source(ref, load)
        rows.extend(found)
        sources.append(source)
    return rows, sources


def run(root, args, context, invoke=None, load=None, save=None):
    options(args, ('refs', 'query', 'limit', 'maxBytes'))
    identity(context)
    refs = _references(args)
    query = text(args.get('query'), 'query', 2000)
    limit = integer(args, 'limit', 1, 40, 12)
    budget = integer(args, 'maxBytes', 1024, 24576, 12288)
    rows, sources = _collect(refs, callback(load, 'load'))
    ranked = evidence_index_query.ranked(rows, query, limit + 1)
    selected, used = evidence_index_query.select(ranked[:limit], budget)
    result = evidence_index_budget.bounded(_result(selected, ranked, sources, used), budget)
    result['returnedBytes'] = sum(len(row['text'].encode('utf-8')) for row in result['items'])
    return result


def _state(selected, sources):
    if selected:
        return 'collected'
    if any(source['status'] == 'available' for source in sources):
        return 'no_match'
    return 'unavailable'


def _result(selected, ranked, sources, used):
    all_scanned = all(source.get('scanComplete', False) for source in sources)
    selection_complete = len(selected) == len(ranked)
    return {'kind': 'evidence-packet', 'schemaVersion': 1,
            'status': 'completed' if all_scanned and selection_complete else 'partial',
            'operation': 'evidence', 'effectState': 'none', 'items': selected,
            'evidenceState': _state(selected, sources),
            'coverage': {'sourceScanComplete': all_scanned, 'selectionComplete': selection_complete},
            'continuations': [{'operation': 'ops_result', 'view': 'raw',
                               'instruction': 'Use returned source ref/pointer/offset; narrow refs/query if packet metadata was omitted.'}],
            'sources': sources, 'scanComplete': all_scanned,
            'selectionComplete': selection_complete, 'returnedBytes': used,
            'matching': 'SQLite FTS5 unicode61 lexical OR; no semantic translation or source reread',
            'sourceCompleteness': 'Only authorized saved observations; inspect per-source coverage',
            'nextAction': 'Use each item ref/pointer/offset for exact original evidence; narrow query for omitted matches.'}
