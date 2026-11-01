"""Select recorded time/turn cohorts without guessing task or version labels."""
from datetime import datetime
import math


def boundary(value):
    if value is None:
        return None
    if isinstance(value, str):
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if date.tzinfo is None:
            raise ValueError('Cohort timestamps require an explicit timezone')
        return date.timestamp()
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Cohort bounds must be finite timestamps')
    return value


def _timestamp(record):
    try:
        return boundary(record.get('timestamp'))
    except (ValueError, TypeError, OverflowError):
        return None


def _turn(record):
    payload = record.get('payload', {})
    return payload.get('turn_id') or record.get('_turnId')


def _time_selected(record, since, until):
    if since is None and until is None:
        return True
    stamp = _timestamp(record)
    return stamp is not None and _in_range(stamp, since, until)


def _in_range(stamp, since, until):
    return (since is None or stamp >= since) and (until is None or stamp < until)


def _matches(record, since, until, turn_id):
    if turn_id is not None and _turn(record) != turn_id:
        return False
    return _time_selected(record, since, until)


def select(records, since=None, until=None, turn_id=None):
    since, until = boundary(since), boundary(until)
    if since is not None and until is not None and since >= until:
        raise ValueError('Cohort since must precede until')
    selected = [row for row in records if _matches(row, since, until, turn_id)]
    return selected, {'since': since, 'until': until, 'turnId': turn_id,
                      'selectedRecords': len(selected), 'excludedRecords': len(records) - len(selected),
                      'versionAttribution': 'Request usage has no plugin version; never infer it from current installation',
                      'originAttribution': 'Rollouts do not label production versus validation; explicit cohort required'}
