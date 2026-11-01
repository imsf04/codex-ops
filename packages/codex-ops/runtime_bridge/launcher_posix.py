"""Opt-in POSIX app-server launcher with owned bridge process groups."""
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import sys
import time

VALUE_OPTIONS = frozenset(('-c', '--config', '-m', '--model', '-p', '--profile', '-s', '--sandbox',
                           '-a', '--ask-for-approval', '-C', '--cd', '--add-dir', '--enable', '--disable',
                           '--image', '-i', '--listen', '--code-mode-host', '--startup-client-info',
                           '--cloud-skills-snapshot', '--ws-auth', '--ws-token-file', '--ws-token-sha256',
                           '--ws-shared-secret-file', '--ws-issuer', '--ws-audience', '--ws-max-clock-skew-seconds'))
BRIDGE_ENV = ('CODEX_OPS_AUTO_OUTPUT', 'CODEX_OPS_BRIDGE_MANAGER_PID', 'CODEX_OPS_BRIDGE_SHIM_PID')


def service_index(arguments):
    command = None
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in ('--help', '-h', '--version', '-V', '--print-startup-config'):
            return None
        if argument in VALUE_OPTIONS:
            index += 2
            continue
        if not argument.startswith('-'):
            if command is None and argument == 'app-server':
                command = index
            else:
                return None
        index += 1
    return command


def _explicit_host(arguments, index):
    index += 1
    while index < len(arguments):
        value = arguments[index]
        if value == '--code-mode-host' or value.startswith('--code-mode-host='):
            return True
        index += 2 if value in VALUE_OPTIONS else 1
    return False


def _exited(pid):
    status = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    if status is not None and status.si_code == os.CLD_STOPPED:
        os.waitid(os.P_PID, pid, os.WSTOPPED | os.WNOHANG)
        return None
    return status


def _stop_group(process, signum):
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass
    except PermissionError:
        # macOS can report EPERM when the group contains only an exited leader.
        if _exited(process.pid) is None:
            raise


def _ready(process, heartbeat):
    deadline = time.monotonic() + 10
    data = b''
    while time.monotonic() < deadline and len(data) <= 4096:
        if _exited(process.pid) is not None:
            break
        ready, _, _ = select.select([process.stdout, heartbeat], [], [], min(.1, max(0, deadline - time.monotonic())))
        if heartbeat in ready and not os.read(heartbeat, 1):
            raise BrokenPipeError('Launcher exited during bridge startup')
        if process.stdout in ready:
            part = os.read(process.stdout.fileno(), 4097 - len(data))
            if not part:
                break
            data += part
            if b'\n' in data:
                endpoint = data.split(b'\n', 1)[0].decode('ascii').strip()
                if re.fullmatch(r'http://127\.0\.0\.1:[1-9][0-9]{0,4}', endpoint):
                    port = int(endpoint.rsplit(':', 1)[1])
                    if port <= 65535:
                        return endpoint
                break
    raise RuntimeError('Bridge did not return a valid loopback address')


def _cleanup(processes):
    failures = []
    for signum in (signal.SIGTERM, signal.SIGKILL):
        if signum == signal.SIGKILL and processes:
            time.sleep(.2)
        for process in processes:
            try:
                _stop_group(process, signum)
            except OSError as error:
                failures.append(str(error))
    for process in processes:
        try:
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired) as error:
            failures.append(str(error))
        if process.stdout:
            process.stdout.close()
    return failures


def _supervise(cli, manager_path, arguments, index, heartbeat, result, launcher_pid):
    processes = []
    code = 1
    try:
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(signum, lambda *_: None)
        host = Path(cli).with_name('codex-code-mode-host')
        endpoint = None
        if host.is_file():
            try:
                environment = {**os.environ, 'CODEX_OPS_BRIDGE_SHIM_PID': str(launcher_pid)}
                manager = subprocess.Popen([sys.executable, str(manager_path), '--native-host', str(host)],
                                           env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                           start_new_session=True)
                processes.append(manager)
                endpoint = _ready(manager, heartbeat)
                if _exited(manager.pid) is not None:
                    raise RuntimeError('Bridge exited during startup')
            except BrokenPipeError:
                return
            except (OSError, RuntimeError, UnicodeError) as error:
                endpoint = None
                print(f'codex-ops: {error}; using native output.', file=sys.stderr)
        else:
            print('codex-ops: native Code Mode host unavailable; using native output.', file=sys.stderr)
        environment = dict(os.environ)
        for key in BRIDGE_ENV:
            environment.pop(key, None)
        if endpoint:
            arguments = [*arguments[:index + 1], '--code-mode-host', endpoint, *arguments[index + 1:]]
            environment.update(CODEX_OPS_AUTO_OUTPUT='1', CODEX_OPS_BRIDGE_MANAGER_PID=str(manager.pid),
                               CODEX_OPS_BRIDGE_SHIM_PID=str(launcher_pid))
        server = subprocess.Popen([cli, *arguments], env=environment, start_new_session=True)
        processes.append(server)
        while True:
            ready, _, _ = select.select([heartbeat], [], [], .1)
            if ready and not os.read(heartbeat, 1):
                break
            status = _exited(server.pid)
            if status is not None:
                code = status.si_status if status.si_code == os.CLD_EXITED else 128 + status.si_status
                break
    except (OSError, ValueError) as error:
        print(f'codex-ops: {error}', file=sys.stderr)
    finally:
        failures = _cleanup(processes)
        if failures:
            print('codex-ops: process cleanup failed: ' + '; '.join(failures), file=sys.stderr)
            code = 1
        try:
            os.write(result, str(code).encode('ascii'))
        except BrokenPipeError:
            pass
        os.close(heartbeat)
        os.close(result)


def main(arguments=None, *, cli=None, manager=None):
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    cli = cli or os.environ.get('CODEX_OPS_REAL_CLI')
    if not cli or not Path(cli).is_file():
        raise SystemExit('Set CODEX_OPS_REAL_CLI to the native Codex executable')
    index = service_index(arguments)
    if index is None:
        os.execv(cli, [cli, *arguments])
    proxy = any(os.environ.get(key) for key in ('HTTP_PROXY', 'http_proxy', 'ALL_PROXY', 'all_proxy'))
    if _explicit_host(arguments, index) or proxy:
        if proxy and not _explicit_host(arguments, index):
            print('codex-ops: HTTP proxy may intercept the native host; using native output.', file=sys.stderr)
        environment = {key: value for key, value in os.environ.items() if key not in BRIDGE_ENV}
        os.execve(cli, [cli, *arguments], environment)
    manager = manager or str(Path(__file__).with_name('manager.py'))
    heartbeat_r, heartbeat_w = os.pipe()
    result_r, result_w = os.pipe()
    launcher_pid = os.getpid()
    guardian = os.fork()
    if guardian == 0:
        os.close(heartbeat_w)
        os.close(result_r)
        _supervise(cli, manager, arguments, index, heartbeat_r, result_w, launcher_pid)
        os._exit(0)
    os.close(heartbeat_r)
    os.close(result_w)
    try:
        code = os.read(result_r, 16)
    finally:
        os.close(heartbeat_w)
        os.close(result_r)
        os.waitpid(guardian, 0)
    raise SystemExit(int(code) if code else 1)


if __name__ == '__main__':
    main()
