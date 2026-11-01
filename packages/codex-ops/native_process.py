"""One-shot native execution with measured starts and deterministic child cleanup."""
import os
import subprocess

import cost_events


def run(command, payload, timeout, operation):
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, creationflags=flags) as process:
        cost_events.worker(operation)
        try:
            stdout, stderr = process.communicate(payload, timeout=timeout)
        except BaseException:
            process.kill()
            process.communicate()
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
