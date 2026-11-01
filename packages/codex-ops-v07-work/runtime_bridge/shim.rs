//! Desktop CLI override: add the local Code Mode host only to app-server service starts.
//! No binary patching, PATH mutation, authentication changes or package-identity synthesis.
#![cfg_attr(windows, windows_subsystem = "windows")]

use std::env;
use std::ffi::{c_void, OsStr, OsString};
use std::fs;
use std::io::{self, BufRead, BufReader, Read};
use std::os::windows::io::AsRawHandle;
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, SystemTime};

const CREATE_SUSPENDED: u32 = 0x0000_0004;
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const KILL_ON_JOB_CLOSE: u32 = 0x0000_2000;
type Handle = *mut c_void;
#[cfg(test)]
static LAST_TEST_CHILD: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);

#[repr(C)]
#[derive(Default)]
struct BasicLimits {
    process_time: i64,
    job_time: i64,
    flags: u32,
    min_working_set: usize,
    max_working_set: usize,
    active_process_limit: u32,
    affinity: usize,
    priority_class: u32,
    scheduling_class: u32,
}

#[repr(C)]
#[derive(Default)]
struct ExtendedLimits {
    basic: BasicLimits,
    io_counters: [u64; 6],
    process_memory_limit: usize,
    job_memory_limit: usize,
    peak_process_memory: usize,
    peak_job_memory: usize,
}

#[repr(C)]
#[derive(Default)]
struct ThreadEntry {
    size: u32,
    usage: u32,
    thread_id: u32,
    owner_pid: u32,
    base_priority: i32,
    delta_priority: i32,
    flags: u32,
}

#[link(name = "kernel32")]
unsafe extern "system" {
    fn CreateJobObjectW(attributes: Handle, name: *const u16) -> Handle;
    fn SetInformationJobObject(job: Handle, class: i32, information: Handle, size: u32) -> i32;
    fn AssignProcessToJobObject(job: Handle, process: Handle) -> i32;
    fn CloseHandle(handle: Handle) -> i32;
    fn CreateToolhelp32Snapshot(flags: u32, process_id: u32) -> Handle;
    fn Thread32First(snapshot: Handle, entry: *mut ThreadEntry) -> i32;
    fn Thread32Next(snapshot: Handle, entry: *mut ThreadEntry) -> i32;
    fn OpenThread(access: u32, inherit: i32, thread_id: u32) -> Handle;
    fn ResumeThread(thread: Handle) -> u32;
}

struct OwnedHandle(Handle);
impl Drop for OwnedHandle {
    fn drop(&mut self) {
        unsafe { CloseHandle(self.0); }
    }
}

struct Job(OwnedHandle);
enum SpawnError { Process(io::Error), Lifecycle(io::Error) }
impl From<SpawnError> for io::Error {
    fn from(error: SpawnError) -> Self {
        match error { SpawnError::Process(error) | SpawnError::Lifecycle(error) => error }
    }
}
impl Job {
    fn new() -> io::Result<Self> {
        let raw = unsafe { CreateJobObjectW(std::ptr::null_mut(), std::ptr::null()) };
        if raw.is_null() { return Err(io::Error::last_os_error()); }
        let owned = OwnedHandle(raw);
        let mut limits = ExtendedLimits::default();
        limits.basic.flags = KILL_ON_JOB_CLOSE;
        let ok = unsafe {
            SetInformationJobObject(raw, 9, &mut limits as *mut _ as Handle,
                                    std::mem::size_of::<ExtendedLimits>() as u32)
        };
        if ok == 0 { return Err(io::Error::last_os_error()); }
        Ok(Self(owned))
    }

    fn spawn(&self, command: &mut Command) -> Result<Child, SpawnError> {
        command.creation_flags(CREATE_NO_WINDOW | CREATE_SUSPENDED);
        let mut child = command.spawn().map_err(SpawnError::Process)?;
        #[cfg(test)]
        LAST_TEST_CHILD.store(child.id(), std::sync::atomic::Ordering::SeqCst);
        let assigned = unsafe { AssignProcessToJobObject(self.0.0, child.as_raw_handle()) };
        if assigned == 0 {
            let error = io::Error::last_os_error();
            let _ = child.kill();
            let _ = child.wait();
            return Err(SpawnError::Lifecycle(error));
        }
        if let Err(error) = resume_initial_thread(child.id()) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(SpawnError::Lifecycle(error));
        }
        Ok(child)
    }
}

fn resume_initial_thread(pid: u32) -> io::Result<()> {
    let raw = unsafe { CreateToolhelp32Snapshot(0x0000_0004, 0) };
    if raw == (-1isize) as Handle { return Err(io::Error::last_os_error()); }
    let snapshot = OwnedHandle(raw);
    let mut entry = ThreadEntry { size: std::mem::size_of::<ThreadEntry>() as u32, ..Default::default() };
    let mut found = unsafe { Thread32First(snapshot.0, &mut entry) };
    while found != 0 {
        if entry.owner_pid == pid {
            let raw = unsafe { OpenThread(0x0002, 0, entry.thread_id) };
            if raw.is_null() { return Err(io::Error::last_os_error()); }
            let thread = OwnedHandle(raw);
            if unsafe { ResumeThread(thread.0) } == u32::MAX {
                return Err(io::Error::last_os_error());
            }
            return Ok(());
        }
        found = unsafe { Thread32Next(snapshot.0, &mut entry) };
    }
    Err(io::Error::new(io::ErrorKind::NotFound, "suspended child has no initial thread"))
}

fn same_path(left: &Path, right: &Path) -> bool {
    let left = fs::canonicalize(left).unwrap_or_else(|_| left.to_path_buf());
    let right = fs::canonicalize(right).unwrap_or_else(|_| right.to_path_buf());
    left.as_os_str().to_string_lossy().eq_ignore_ascii_case(&right.as_os_str().to_string_lossy())
}

fn configured_path(directory: &Path, name: &str) -> io::Result<PathBuf> {
    let text = fs::read_to_string(directory.join(name))?;
    let path = text.trim_start_matches('\u{feff}').trim();
    if path.is_empty() || path.contains(['\n', '\r', '\0']) {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "path configuration requires one line"));
    }
    let path = PathBuf::from(path);
    if !path.is_absolute() || !path.is_file() {
        return Err(io::Error::new(io::ErrorKind::NotFound, "configured absolute file is unavailable"));
    }
    Ok(path)
}

fn real_cli(directory: &Path, executable: &Path) -> io::Result<PathBuf> {
    if let Ok(path) = configured_path(directory, "real-cli.txt") {
        if !same_path(&path, executable) { return Ok(path); }
    }
    if let Some(paths) = env::var_os("PATH") {
        for directory in env::split_paths(&paths) {
            let path = directory.join("codex.exe");
            if path.is_file() && !same_path(&path, executable) { return Ok(path); }
        }
    }
    if let Some(local) = env::var_os("LOCALAPPDATA") {
        let base = PathBuf::from(local).join("OpenAI/Codex/bin");
        let mut candidates = Vec::new();
        if let Ok(entries) = fs::read_dir(base) {
            for entry in entries.flatten() {
                let path = entry.path().join("codex.exe");
                if path.is_file() && !same_path(&path, executable) {
                    let time = fs::metadata(&path).and_then(|m| m.modified()).unwrap_or(SystemTime::UNIX_EPOCH);
                    candidates.push((time, path));
                }
            }
        }
        candidates.sort_by(|left, right| right.0.cmp(&left.0));
        if let Some((_, path)) = candidates.into_iter().next() { return Ok(path); }
    }
    Err(io::Error::new(io::ErrorKind::NotFound, "native Codex CLI was not found"))
}

fn takes_value(argument: &OsStr) -> bool {
    matches!(argument.to_str(), Some("-c" | "--config" | "-m" | "--model" | "-p" | "--profile"
        | "-s" | "--sandbox" | "-a" | "--ask-for-approval" | "-C" | "--cd" | "--add-dir"
        | "--enable" | "--disable" | "--image" | "-i" | "--listen" | "--code-mode-host"
        | "--startup-client-info" | "--cloud-skills-snapshot" | "--ws-auth" | "--ws-token-file"
        | "--ws-token-sha256" | "--ws-shared-secret-file" | "--ws-issuer" | "--ws-audience"
        | "--ws-max-clock-skew-seconds"))
}

fn service_index(arguments: &[OsString]) -> Option<usize> {
    let mut index = 0;
    let mut command = None;
    while index < arguments.len() {
        let argument = &arguments[index];
        if matches!(argument.to_str(), Some("--help" | "-h" | "--version" | "-V" | "--print-startup-config")) {
            return None;
        }
        if takes_value(argument) { index += 2; continue; }
        if !argument.to_string_lossy().starts_with('-') {
            if command.is_none() && argument == "app-server" {
                command = Some(index);
            } else {
                // Any explicit app-server subcommand (or another root command)
                // is passthrough, including future subcommands not known here.
                return None;
            }
        }
        index += 1;
    }
    command
}

fn explicit_host(arguments: &[OsString], start: usize) -> bool {
    let mut index = start + 1;
    while index < arguments.len() {
        let argument = &arguments[index];
        if argument == "--code-mode-host" || argument.to_string_lossy().starts_with("--code-mode-host=") {
            return true;
        }
        index += if takes_value(argument) { 2 } else { 1 };
    }
    false
}

struct Manager {
    _job: Job,
    child: Child,
}

enum BridgeError { Unavailable(String), Lifecycle(io::Error) }
impl From<&str> for BridgeError {
    fn from(message: &str) -> Self { Self::Unavailable(message.to_owned()) }
}
impl From<String> for BridgeError {
    fn from(message: String) -> Self { Self::Unavailable(message) }
}

fn start_manager(directory: &Path, native_cli: &Path) -> Result<(Manager, String), BridgeError> {
    let python = configured_path(directory, "bridge-python.txt").map_err(|_| "bridge Python is unavailable")?;
    let script = configured_path(directory, "bridge-script.txt").map_err(|_| "bridge manager is unavailable")?;
    let native_host = native_cli.with_file_name("codex-code-mode-host.exe");
    if !native_host.is_file() { return Err("native Code Mode host is unavailable".into()); }
    let job = Job::new().map_err(BridgeError::Lifecycle)?;
    let child = job.spawn(Command::new(python).arg(script).arg("--native-host").arg(native_host)
                          .env("CODEX_OPS_BRIDGE_SHIM_PID", std::process::id().to_string())
                          .stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::inherit()))
        .map_err(|error| match error {
            SpawnError::Process(error) => BridgeError::Unavailable(format!("bridge process could not start: {error}")),
            SpawnError::Lifecycle(error) => BridgeError::Lifecycle(error),
        })?;
    let mut manager = Manager { _job: job, child };
    let stdout = manager.child.stdout.take().ok_or("bridge stdout unavailable")?;
    let (sender, receiver) = mpsc::channel();
    thread::spawn(move || {
        let mut line = String::new();
        let result = BufReader::new(stdout.take(4097)).read_line(&mut line).map(|_| line);
        let _ = sender.send(result);
    });
    let line = receiver.recv_timeout(Duration::from_secs(10)).map_err(|_| "bridge readiness timed out")?
        .map_err(|_| "bridge readiness could not be read")?;
    let endpoint = line.trim_end_matches(['\r', '\n']);
    let port = endpoint.strip_prefix("http://127.0.0.1:").and_then(|value| value.parse::<u16>().ok());
    if port.is_none() || port == Some(0) { return Err("bridge returned an invalid loopback endpoint".into()); }
    if manager.child.try_wait().map_err(|_| "bridge state unavailable")?.is_some() {
        return Err("bridge exited during startup".into());
    }
    Ok((manager, endpoint.to_owned()))
}

fn run() -> io::Result<i32> {
    let executable = env::current_exe()?;
    let directory = executable.parent().ok_or_else(|| io::Error::other("shim path has no directory"))?;
    let native_cli = real_cli(directory, &executable)?;
    let mut arguments: Vec<OsString> = env::args_os().skip(1).collect();
    let service = service_index(&arguments);
    let mut manager = None;
    // Only long-lived app-server service starts are owned. Intentional daemon,
    // login/browser and other CLI child lifetimes retain native behavior.
    let job = if service.is_some() { Some(Job::new()?) } else { None };
    if let Some(index) = service {
        if !explicit_host(&arguments, index) {
            match start_manager(directory, &native_cli) {
                Ok((owned, endpoint)) => {
                    arguments.insert(index + 1, "--code-mode-host".into());
                    arguments.insert(index + 2, endpoint.into());
                    manager = Some(owned);
                }
                Err(BridgeError::Unavailable(message)) => eprintln!("codex-ops: {message}; using native output."),
                Err(BridgeError::Lifecycle(error)) => return Err(error),
            }
        }
    }
    let mut command = Command::new(native_cli);
    command.args(arguments).stdin(Stdio::inherit()).stdout(Stdio::inherit()).stderr(Stdio::inherit());
    if let Some(manager) = &manager {
        command.env("CODEX_OPS_AUTO_OUTPUT", "1");
        command.env("CODEX_OPS_BRIDGE_MANAGER_PID", manager.child.id().to_string());
        command.env("CODEX_OPS_BRIDGE_SHIM_PID", std::process::id().to_string());
    } else if service.is_some() {
        command.env_remove("CODEX_OPS_AUTO_OUTPUT");
        command.env_remove("CODEX_OPS_BRIDGE_MANAGER_PID");
        command.env_remove("CODEX_OPS_BRIDGE_SHIM_PID");
    }
    let mut child = if let Some(job) = &job {
        job.spawn(&mut command)?
    } else {
        command.creation_flags(CREATE_NO_WINDOW).spawn()?
    };
    let status = child.wait()?;
    // Closing these handles also cleans grandchildren after graceful native exit.
    drop(manager);
    drop(job);
    Ok(status.code().unwrap_or(1))
}

fn main() {
    let code = match run() {
        Ok(code) => code,
        Err(error) => {
            eprintln!("codex-ops: cannot start CLI safely: {error}");
            1
        }
    };
    std::process::exit(code);
}

#[cfg(test)]
mod tests {
    use super::*;
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn OpenProcess(access: u32, inherit: i32, pid: u32) -> Handle;
        fn WaitForSingleObject(handle: Handle, milliseconds: u32) -> u32;
    }

    #[test]
    fn failed_assignment_terminates_and_reaps_suspended_child() {
        let invalid_job = Job(OwnedHandle(std::ptr::null_mut()));
        let system = env::var_os("SystemRoot").unwrap();
        let result = invalid_job.spawn(Command::new(PathBuf::from(system).join("System32/cmd.exe"))
            .args(["/d", "/c", "exit", "0"]).stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null()));
        assert!(result.is_err(), "invalid job must never run an unowned child");
        let pid = LAST_TEST_CHILD.load(std::sync::atomic::Ordering::SeqCst);
        assert_ne!(pid, 0);
        let raw = unsafe { OpenProcess(0x0010_0000, 0, pid) };
        if !raw.is_null() {
            let owned = OwnedHandle(raw);
            assert_eq!(unsafe { WaitForSingleObject(owned.0, 0) }, 0,
                       "failed assignment left a suspended orphan process");
        }
    }
}
