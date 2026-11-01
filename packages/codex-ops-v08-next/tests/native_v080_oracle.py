"""Evaluate unchanged outcome contracts inside the configured native sandbox."""
import argparse
import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v080_model_tasks import evaluate_task

parser = argparse.ArgumentParser()
parser.add_argument('--task', required=True)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--expected', required=True)
args = parser.parse_args()
expected = json.loads(base64.b64decode(args.expected))
print(json.dumps(evaluate_task(args.task, args.root, expected), ensure_ascii=False))
