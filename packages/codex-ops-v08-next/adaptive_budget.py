"""A small policy driven only by attributable immediate presentation rereads."""


def recommend(observations, current_bytes=12288):
    _validate(current_bytes)
    usable = _usable(observations)
    rereads = sum(event.get('immediateReread') is True for event in usable)
    budget = _next(current_bytes, len(usable), rereads)
    return {'currentBytes': current_bytes, 'recommendedBytes': budget,
            'eligibleObservations': len(usable), 'immediateRereads': rereads,
            'reason': 'suspected-presentation-rereads' if budget > current_bytes else 'insufficient-evidence-or-no-change',
            'measurement': 'Presentation budget suggestion, not measured savings; never changes internal values.'}


def _validate(current_bytes):
    if type(current_bytes) is not int or not 4096 <= current_bytes <= 24576:
        raise ValueError('Evidence budget must be 4096..24576 bytes')


def _usable(observations):
    usable = [event for event in observations if _eligible(event)]
    if len({event['chatId'] for event in usable}) != 1:
        return []
    return usable


def _eligible(event):
    if not isinstance(event, dict) or event.get('origin') != 'production':
        return False
    return bool(event.get('chatId')) and event.get('attributed') is True and event.get('reason') == 'presentation'


def _next(current, count, rereads):
    if count < 4 or rereads < 2:
        return current
    if rereads / count < 0.5:
        return current
    return min(24576, current + 4096)
