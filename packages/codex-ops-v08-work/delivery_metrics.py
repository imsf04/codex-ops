"""Count automatic analysis only after its evidence actually reaches a display."""
import json

import cost_events


def _served(value):
    if not isinstance(value, dict):
        return False
    if value.get('kind') != 'native-observation':
        return False
    return type(value.get('exit_code')) is int or type(value.get('session_id')) is int


def record_delivered(displayed):
    try:
        value = json.loads(displayed)
    except (ValueError, TypeError):
        return False
    if not isinstance(value, dict) or not _served(value.get('preview')):
        return False
    return cost_events.record('automatic', 'verify', outcome='completed', evidence='present')
