"""Wait for the telemetry event a native probe actually exercised."""
import json
import time


def wait_for_status(path, *, projected, timeout=4):
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        if path.exists():
            status = json.loads(path.read_text(encoding='utf-8'))
            counts = status['counters']
            if counts['outboundFrames'] >= 4 and (not projected or counts['compactedFrames'] > 0):
                return status
        time.sleep(.1)
    raise AssertionError(f'Bridge did not publish the expected telemetry before timeout: {status}')
