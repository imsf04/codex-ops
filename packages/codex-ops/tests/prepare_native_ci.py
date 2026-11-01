"""Extract the pinned native test host and expose it to subsequent CI steps."""
import os
from pathlib import Path
import sys

from check_portable_bundle import native_cli


def prepare(archives, destination):
    destination.mkdir(parents=True, exist_ok=True)
    cli = native_cli(archives, destination)
    native_cli(archives, destination, 'codex-code-mode-host')
    with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as output:
        output.write(f'CODEX_APP_RUNTIME_CLI_PATH={cli}\n')
    with open(os.environ['GITHUB_PATH'], 'a', encoding='utf-8') as output:
        output.write(str(destination) + '\n')


if __name__ == '__main__':
    prepare(Path(sys.argv[1]), Path(sys.argv[2]))
