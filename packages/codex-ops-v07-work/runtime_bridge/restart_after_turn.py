"""One-shot normal Desktop quit/relaunch after this chat's final response is saved.

Never accept a quit confirmation or terminate a process. This helper is not an
installed service; it exits after verification or after the bounded wait expires.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time

from control import alive, launch, status


def completed(line, turn):
    try:
        event = json.loads(line)
        value = event.get('payload', {})
        return event.get('type') == 'event_msg' and value.get('type') == 'task_complete' and value.get('turn_id') == turn
    except (ValueError, TypeError, AttributeError):
        return False


def normal_quit(pid, window):
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.GetForegroundWindow.restype = wintypes.HWND
    user.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wintypes.DWORD, ctypes.c_size_t]
    owner = wintypes.DWORD()
    user.GetWindowThreadProcessId(window, ctypes.byref(owner))
    if owner.value != pid:
        return False
    user.ShowWindow(window, 9)  # Restore, then target only the verified Desktop window.
    user.SetForegroundWindow(window)
    time.sleep(0.25)
    if user.GetForegroundWindow() != window:
        return False
    # Verified Windows native menu accelerator; normal app.quit lifecycle applies.
    user.keybd_event(0x11, 0, 0, 0)
    user.keybd_event(0x51, 0, 0, 0)
    user.keybd_event(0x51, 0, 2, 0)
    user.keybd_event(0x11, 0, 2, 0)
    return True


def parents():
    # Process identities only; no command lines or environments are inspected.
    import subprocess
    query = 'Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json -Compress'
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', query], capture_output=True,
                            text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return {p['ProcessId']: p for p in json.loads(result.stdout)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rollout', required=True, type=Path)
    parser.add_argument('--turn', required=True)
    parser.add_argument('--desktop-pid', required=True, type=int)
    parser.add_argument('--window', required=True, type=int)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    def record(state, **details):
        args.receipt.write_text(json.dumps({'state': state, 'updatedAt': time.time(),
                                          'desktopBefore': args.desktop_pid, **details}, indent=2), encoding='utf-8')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    contained = wintypes.BOOL()
    if not kernel.IsProcessInJob(kernel.GetCurrentProcess(), None, ctypes.byref(contained)) or contained.value:
        record('manual-restart-needed', reason='Helper cannot establish independence from the current process job')
        return
    record('waiting-for-turn-completion')
    with args.rollout.open('rb') as stream:
        stream.seek(0, 2)
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            line = stream.readline()
            if line and not line.endswith(b'\n'):
                stream.seek(-len(line), 1)
                time.sleep(0.2)
                continue
            if line and completed(line, args.turn):
                break
            time.sleep(0.2)
        else:
            record('manual-restart-needed', reason='Turn did not finish within the one-shot wait')
            return
    time.sleep(2)  # Let the completed response reach the visible chat.
    sent = normal_quit(args.desktop_pid, args.window) if alive(args.desktop_pid) else False
    record('waiting-for-normal-desktop-exit', quitAcceleratorSent=sent,
           note='Native confirmation, if present, is left to the user; no force kill')
    deadline = time.monotonic() + 1800
    while alive(args.desktop_pid) and time.monotonic() < deadline:
        time.sleep(0.5)
    if alive(args.desktop_pid):
        record('manual-restart-needed', reason='Desktop remained open; no process was terminated')
        return
    launched = launch()
    record('desktop-launched', launch=launched)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        running = status()
        if running['activeInstances']:
            tree = parents()
            for instance in running['activeInstances']:
                shim = tree.get(instance['shimPid'], {})
                desktop = tree.get(shim.get('ParentProcessId'), {})
                if desktop.get('Name', '').lower() == 'chatgpt.exe' and instance['compressionEnabled']:
                    record('desktop-bridge-active', desktopAfter=desktop['ProcessId'],
                           shimPid=instance['shimPid'], instance=instance,
                           note='Actual Desktop owns the staged shim and ready host relay; staged exec fixtures passed before activation')
                    return
        time.sleep(1)
    record('activation-unverified', launch=launched, runtime=status())


if __name__ == '__main__':
    main()
