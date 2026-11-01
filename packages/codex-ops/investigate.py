"""Bounded discovery then context expansion through the permissioned adapter."""
import evidence_packet
import investigate_query
import investigate_plan


def _failed(stage):
    return stage['result'].get('status') in ('error', 'rejected', 'failed')


def _failure(stages):
    for stage in stages:
        if _failed(stage):
            return stage['result']
    return None


def run(root, args, invoke):
    query = investigate_query.parse(args)
    if not query['anchors']:
        return evidence_packet.needs_anchor(query)
    observed = invoke(root, 'investigate', investigate_plan.build(root, query))
    if observed.get('status') in ('error', 'rejected', 'failed'):
        return observed
    stages = observed['stages']
    failure = _failure(stages)
    if failure and all(_failed(stage) for stage in stages):
        return failure
    query['kernel'] = observed['kernel']
    return evidence_packet.build(query, stages)
