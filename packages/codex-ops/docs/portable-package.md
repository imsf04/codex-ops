# Portable package preview

This preview installs the MCP server, skills, hooks and platform-native worker and kernel. It needs
internet access on first install to obtain Python 3.14 and locked Python dependencies. Keep the
extracted directory in place: installed commands refer to it. Re-run the installer and reinstall the
plugin if it moves.

On Windows run `powershell -ExecutionPolicy Bypass -File ./install.ps1`. On Linux or macOS run
`sh ./install.sh`. Then register and install the plugin from the extracted directory:

```console
codex plugin marketplace add .
codex plugin add codex-ops@codex-ops-portable
```

Review and trust the installed hook definitions through Codex before using them. A direct hook
execution test does not establish host trust. Python, packages and local observation data remain on
the local machine.

The Windows automatic-output bridge is optional and requires a separately validated native host;
the installer does not enable it. From the extracted directory, stage and enable it with:

```powershell
$env:CODEX_OPS_BRIDGE_PYTHON = (Resolve-Path ./plugin/.venv/Scripts/python.exe).Path
& $env:CODEX_OPS_BRIDGE_PYTHON ./plugin/runtime_bridge/control.py stage
& $env:CODEX_OPS_BRIDGE_PYTHON ./plugin/runtime_bridge/control.py enable
```

An existing runtime with the same version must not be overwritten; stage reports a mismatch. Check
the bridge status after restarting Desktop.

On Linux and macOS, the installer also prepares `plugin/bin/codex-ops-cli`. To try the launcher, set
`CODEX_OPS_REAL_CLI` to the native Codex executable whose directory also contains
`codex-code-mode-host`, then configure the host that starts `app-server` to use that launcher. It
enables compression only for the validated Codex CLI 0.165.0-alpha.1 host hashes on Linux x64,
macOS ARM64 and macOS x64; unvalidated native hosts are forwarded unchanged. It falls back to native
output when an HTTP proxy is set.
For a direct app-server session, run:

```sh
CODEX_OPS_REAL_CLI=/absolute/path/to/codex ./plugin/bin/codex-ops-cli app-server --stdio
```

For a host that honors `CODEX_CLI_PATH`, set it to the absolute path of this launcher in that
host's launch environment and set `CODEX_OPS_REAL_CLI` there too. Fully restart the host so it
inherits the settings. `ops_stats` reports whether the bridge is attached to the current process.
Desktop GUI activation and additional host versions have not been validated by headless CI.

CI installs the relocated package in an isolated Codex home, trusts and executes its hook through
the real host, and checks text, asynchronous output, errors, images, tool errors, MCP values and
attached runtime status through the packaged launcher. It also runs installed directory tasks and
rollback, the full Python suite and Rust tests. Platform-only skips are reported separately.

Linux and macOS directory tasks authorize the opened directory identity. Each ancestor is opened
without following symlinks, and creation/removal uses the parent descriptor. External renames may
move that authorized directory; effects still apply to it, never to a replacement symlink target.
Windows instead prevents parent renames while the directory operation runs. See [task contracts](tasks.md).
