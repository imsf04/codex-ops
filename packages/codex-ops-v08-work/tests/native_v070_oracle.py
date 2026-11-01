"""Outcome checker run inside the unchanged native workspace sandbox."""
import argparse
import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v070_model_tasks import TASKS, evaluate_task


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', choices=TASKS, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--expected', required=True)
    args = parser.parse_args()
    expected = json.loads(base64.b64decode(args.expected).decode('utf-8'))
    print(json.dumps(evaluate_task(args.task, args.root, expected), ensure_ascii=False))


if __name__ == '__main__':
    main()
