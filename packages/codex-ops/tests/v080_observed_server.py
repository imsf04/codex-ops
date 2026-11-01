"""Observe actual MCP worker starts without changing inputs or returned values."""
import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time


def append(path, value):
    try:
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(value, separators=(',', ':'))+'\n')
    except OSError as exc:
        print('MCP worker observer unavailable: '+str(exc), file=sys.stderr, flush=True)


def executable(command):
    if isinstance(command, (list, tuple)) and command:
        return Path(command[0])
    return None


def install(package, log):
    original = subprocess.Popen
    base = (package/'bin').resolve()

    class ObservedProcess(original):
        def __init__(self, args, *rest, **options):
            super().__init__(args, *rest, **options)
            program = executable(args)
            if program is not None and program.resolve().is_relative_to(base):
                append(log, {'kind':'worker-start','at':time.time(),'pid':self.pid,'binary':program.name})

    subprocess.Popen = ObservedProcess
    append(log, {'kind':'observer-ready','at':time.time(),'boundary':'MCP child binaries under package/bin'})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    root = Path(os.environ['CODEX_OPS_STORE'])
    root.mkdir(parents=True, exist_ok=True)
    install(package, root/'mcp-worker-starts.jsonl')
    sys.path.insert(0, str(package))
    runpy.run_path(str(package/'server.py'), run_name='__main__')


if __name__ == '__main__':
    main()
