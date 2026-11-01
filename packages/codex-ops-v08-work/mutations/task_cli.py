"""Native-shell staged tasks. MCP planning never invokes this execution entrypoint."""
import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = 'mutations'

from . import task_engine
from .cli import _read, _stored_plan


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest='action', required=True)
    source = commands.add_parser('apply').add_mutually_exclusive_group(required=True)
    source.add_argument('--plan')
    source.add_argument('--plan-ref')
    for name in ('status', 'resume', 'rollback', 'cancel'):
        command = commands.add_parser(name)
        command.add_argument('--root', required=True)
        command.add_argument('--id', required=True)
    return result


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def run(args):
    if args.action == 'apply':
        value = _stored_plan(args.plan_ref) if args.plan_ref else _read(args.plan)
        return task_engine.apply(value, started=emit)
    actions = {'status': task_engine.inspect, 'resume': task_engine.resume,
               'rollback': task_engine.rollback, 'cancel': task_engine.cancel}
    return actions[args.action](args.root, args.id)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = run(args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'status': 'error', 'effectState': 'unknown', 'error': str(exc),
                  'nextAction': 'Inspect existing task and child journals before any retry.'}
    emit(result)
    return int(result['status'] in ('error', 'needs-inspection'))


if __name__ == '__main__':
    raise SystemExit(main())
