"""Bounded discovery then context expansion through the permissioned adapter."""
import evidence_packet
import investigate_query


def _stage(root, query, path, expanded, invoke):
    args = investigate_query.search_args(query, path, expanded)
    return {'phase': 'expansion' if expanded else 'discovery', 'args': args,
            'result': invoke(root, 'search', args)}


def _failed(stage):
    return stage['result'].get('status') in ('error', 'rejected', 'failed')


def _paths(stages):
    paths = []
    for stage in stages:
        paths.extend(row['path'] for row in stage['result'].get('matches', []))
    return list(dict.fromkeys(paths))[:4]


def _failure(stages):
    for stage in stages:
        if _failed(stage):
            return stage['result']
    return None


def _expand(root, query, stages, invoke):
    expansions = [_stage(root, query, path, True, invoke) for path in _paths(stages)]
    failed = _failure(expansions)
    return failed if failed else evidence_packet.build(query, stages + expansions)


def run(root, args, invoke):
    query = investigate_query.parse(args)
    if not query['anchors']:
        return evidence_packet.needs_anchor(query)
    stages = [_stage(root, query, path, False, invoke) for path in query['paths']]
    failure = _failure(stages)
    if failure:
        return failure
    return _expand(root, query, stages, invoke)
