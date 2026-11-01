"""Run an isolated test process and terminate any descendants on exit."""
import ctypes
import os
import signal
import subprocess
import tempfile


def run(command, *, env, cwd=None, capture_output=False, text=False, check=False, timeout=None):
    job = None
    if os.name == 'nt':
        import win32job
        job = win32job.CreateJobObject(None, '')
        limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        limits['BasicLimitInformation']['LimitFlags'] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = None
        try:
            process = subprocess.Popen(command, env=env, cwd=cwd,
                                       stdout=output if capture_output else None,
                                       stderr=errors if capture_output else None,
                                       creationflags=4 if job is not None else 0,
                                       start_new_session=job is None)
            if job is not None:
                win32job.AssignProcessToJobObject(job, int(process._handle))
                resume = ctypes.WinDLL('ntdll').NtResumeProcess
                resume.argtypes = [ctypes.c_void_p]
                resume.restype = ctypes.c_long
                if resume(int(process._handle)) != 0:
                    raise OSError('Cannot resume isolated test process')
            returncode = process.wait(timeout=timeout)
        finally:
            if job is not None:
                job.Close()
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait()
            elif process is not None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if process.poll() is None:
                    process.wait()
        output.seek(0)
        errors.seek(0)
        stdout, stderr = (output.read(), errors.read()) if capture_output else (None, None)
        if text and capture_output:
            stdout, stderr = stdout.decode('utf-8'), stderr.decode('utf-8')
        result = subprocess.CompletedProcess(command, returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result
