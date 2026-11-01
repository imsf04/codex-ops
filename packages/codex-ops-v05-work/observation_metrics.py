"""Connect saved observations to their known producer without changing tool results."""
from telemetry import Telemetry
from reducers import encode
import time


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
    return receipt


def retrieval(result, options):
    if 'ref' in result and 'view' in result:
        key = encode(options)
        _measure(lambda meter: meter.record_retrieval(result['ref'], len(encode(result).encode()), key))
    return result
