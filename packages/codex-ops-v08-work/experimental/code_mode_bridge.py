"""Opt-in stdio IPC bridge for the installed native host. Not installed into Codex."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import threading

from presentation import output

MAX_FRAME = 64 * 1024 * 1024


def read_frame(stream):
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise ValueError('Incomplete frame header')
    size = struct.unpack('<I', header)[0]
    if size > MAX_FRAME:
        raise ValueError('Frame exceeds native 64 MiB boundary')
    data = stream.read(size)
    if len(data) != size:
        raise ValueError('Incomplete frame body')
    return header + data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path, required=True)
    args = parser.parse_args()
    process = subprocess.Popen([str(args.upstream)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=sys.stderr, creationflags=subprocess.CREATE_NO_WINDOW)
    def upstream():
        try:
            while (frame := read_frame(sys.stdin.buffer)) is not None:
                # Tool results, notification acknowledgments, control and source
                # all remain byte-identical on the inbound path.
                process.stdin.write(frame)
                process.stdin.flush()
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
        finally:
            process.stdin.close()
    threading.Thread(target=upstream, daemon=True).start()
    try:
        while (frame := read_frame(process.stdout)) is not None:
            try:
                value = json.loads(frame[4:])
                projected = output(value)
                if projected != value:
                    data = json.dumps(projected, ensure_ascii=False, separators=(',', ':')).encode()
                    frame = struct.pack('<I', len(data)) + data
            except (ValueError, TypeError, AttributeError):
                pass  # Unknown future schema is forwarded unmodified.
            sys.stdout.buffer.write(frame)
            sys.stdout.buffer.flush()
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)


if __name__ == '__main__':
    main()
