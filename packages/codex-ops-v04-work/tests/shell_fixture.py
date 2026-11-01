"""Deterministic stdout/stderr and exit codes; never reads or modifies user files."""
import argparse
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument('--long', action='store_true')
parser.add_argument('--fail', action='store_true')
parser.add_argument('--silent', action='store_true')
args = parser.parse_args()
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
for index in range(3):
    print(f'PHASE_{index}_BEGIN', flush=True)
    for row in range(80):
        print(f'{index}:{row}:完整值:' + 'abcdef0123456789' * 8)
    print(f'PHASE_{index}_END', flush=True)
    if args.long and index < 2:
        time.sleep(12)
if args.fail:
    if not args.silent:
        print('STDERR_FAILURE_SENTINEL exit=7', file=sys.stderr, flush=True)
    sys.exit(7)
