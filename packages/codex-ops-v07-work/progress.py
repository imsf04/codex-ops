"""Bounded comparison of native shell progress; never omit a terminal result."""
from collections import OrderedDict
import hashlib
import threading
import time

from reducers import encode


def _session(value):
    if not isinstance(value, dict):
        return None
    session = value.get('session_id')
    if type(session) not in (int, str):
        return None
    return str(session) if 0 < len(str(session)) <= 128 else None


def _running(value):
    return value.get('exit_code') is None and value.get('status', 'running') == 'running'


def _fingerprint(value):
    meaningful = {key: item for key, item in value.items()
                  if key not in ('chunk_id', 'wall_time_seconds', 'original_token_count')}
    return hashlib.sha256(encode(meaningful).encode()).digest()


class Progress:
    def __init__(self, limit=128, ttl=300, clock=time.monotonic):
        self.limit, self.ttl, self.clock = limit, ttl, clock
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def _expire(self, now):
        stale = [key for key, value in self.entries.items() if now - value[1] > self.ttl]
        for key in stale:
            del self.entries[key]

    def _remember(self, key, value, now):
        digest = _fingerprint(value)
        prior = self.entries.pop(key, None)
        repeats = prior[2] + 1 if prior and prior[0] == digest else 0
        self.entries[key] = (digest, now, repeats)
        if len(self.entries) > self.limit:
            self.entries.popitem(last=False)
        return repeats

    def observe(self, analysis):
        if analysis['kind'] != 'shell':
            return None
        value = analysis['value']
        key = _session(value)
        if key is None:
            return None
        with self.lock:
            return self._observe(key, value)

    def _observe(self, key, value):
        now = self.clock()
        self._expire(now)
        if not _running(value):
            self.entries.pop(key, None)
            return None
        repeats = self._remember(key, value, now)
        if not repeats:
            return None
        return {'session_id': value['session_id'], 'status': 'running', 'unchangedPolls': repeats}
