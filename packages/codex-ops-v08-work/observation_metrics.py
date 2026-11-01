"""Connect saved observations to their known producer without changing tool results."""
from telemetry import Telemetry
from reducers import encode
import time
import adaptive_budget_ledger
import cost_events
import task_cost_workflows


def _measure(callback):
    meter = None
    try:
        meter = Telemetry(instance_id='observation-links-' + str(int(time.time() // 86400)))
        callback(meter)
    except Exception:
        pass
    finally:
        if meter is not None:
            meter.close()


def reference(receipt, context):
    if receipt.get('kind') == 'reference':
        _measure(lambda meter: meter.link_reference(receipt['ref'], context))
        adaptive_budget_ledger.record_presentation(receipt['ref'], context.get('session'))
    return receipt


def retrieval(result, options, context=None):
    if 'ref' in result and 'view' in result:
        key = encode(options)
        _measure(lambda meter: meter.record_retrieval(result['ref'], len(encode(result).encode()), key))
        adaptive_budget_ledger.record_retrieval(result['ref'], context, result['view'])
    return result


def workflow(result, operation, context, root):
    assessment = task_cost_workflows.assess(result)
    with cost_events.scope(context, root):
        cost_events.record('workflow', operation, **assessment)
    return result
