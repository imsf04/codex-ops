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
the bridge status after restarting Desktop. On Linux and macOS automatic output bridging and staged
directory creation/removal are not yet available. This preview does not claim complete platform parity.
