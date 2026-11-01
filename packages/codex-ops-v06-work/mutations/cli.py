"""Native shell entry point; deliberately absent from MCP execution tools."""
import argparse
import json
from pathlib import Path
from . import engine
from .paths import MAX_BYTES, require
from .planning import plan, summary


def _read(path):
    path = Path(path)
    require(path.stat().st_size <= 10 * MAX_BYTES, 'Input exceeds 10 MiB')
    return json.loads(path.read_text(encoding='utf-8'))


def _plan(args):
    value = plan(args.root, _read(args.request))
    output = Path(args.output)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False)
    return {**summary(value), 'planFile': str(output.resolve())}


def _stored_plan(reference):
    from cache_reader import load
    return load(reference)


def run(args):
    if args.action == 'plan':
        return _plan(args)
    if args.action == 'apply':
        value = _stored_plan(args.plan_ref) if args.plan_ref else _read(args.plan)
        return engine.apply(value)
    actions = {'status': engine.inspect, 'resume': engine.resume, 'rollback': engine.rollback}
    return actions[args.action](args.root, args.id)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest='action', required=True)
    create = commands.add_parser('plan')
    for option in ('root', 'request', 'output'):
        create.add_argument('--' + option, required=True)
    source = commands.add_parser('apply').add_mutually_exclusive_group(required=True)
    source.add_argument('--plan')
    source.add_argument('--plan-ref')
    for action in ('status', 'resume', 'rollback'):
        command = commands.add_parser(action)
        command.add_argument('--root', required=True)
        command.add_argument('--id', required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        value = run(args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        value = {'status': 'error', 'error': str(exc), 'effectState': 'unknown',
                 'nextAction': 'Inspect the journal and current files before any retry'}
    print(json.dumps(value, ensure_ascii=False))
    return _exitcode(args.action, value)


def _exitcode(action, value):
    if value.get('conflicts') or value['status'] in ('error', 'needs-inspection'):
        return 1
    return 0 if action == 'status' or value['status'] in ('planned', 'completed', 'rolled-back') else 1
