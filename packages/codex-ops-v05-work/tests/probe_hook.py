"""Reviewed deterministic hook fixture. No reads beyond stdin; writes probe logs only."""
import json
import os
from pathlib import Path
import sys

event = json.load(sys.stdin)
with (Path(sys.argv[1]) / 'hooks.jsonl').open('a', encoding='utf-8') as stream:
    stream.write(json.dumps(event) + '\n')
mode = sys.argv[2]
if event.get('transcript_path'):
    transcript = Path(event['transcript_path'])
    if transcript.is_file():
        (Path(sys.argv[1]) / 'transcript-at-hook.jsonl').write_bytes(transcript.read_bytes())
name = event['tool_name']
matches = name in ('Bash', 'mcp__probe__fixture') if mode != 'outer' else name in ('exec', 'functions.exec')
if matches and mode != 'audit':
    if mode == 'observe':
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        os.environ['CODEX_OPS_STORE'] = str(Path(sys.argv[1]) / 'store')
        import hook
        output = hook.process(event)
        with (Path(sys.argv[1]) / 'decisions.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'tool':name,'output':output}) + '\n')
        if output:
            print(json.dumps(output))
    elif mode == 'block':
        print(json.dumps({'decision': 'block', 'reason': 'HOOK_COMPACT'}))
    else:
        print(json.dumps({'continue': False, 'stopReason': 'HOOK_COMPACT'}))
