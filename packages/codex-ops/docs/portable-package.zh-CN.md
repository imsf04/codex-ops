# 可移植插件包预览版

预览版安装 MCP 服务、技能、hooks 和本平台的原生工作进程及内核。首次安装需要联网获取
Python 3.14 和锁定的 Python 依赖。请保留解压后的目录：安装后的命令引用该目录。移动目录后
需要重新运行安装器并重新安装插件。

Windows 运行 `powershell -ExecutionPolicy Bypass -File ./install.ps1`；Linux 或 macOS
运行 `sh ./install.sh`。然后在解压目录中注册并安装插件：

```console
codex plugin marketplace add .
codex plugin add codex-ops@codex-ops-portable
```

使用前请在 Codex 中审阅并信任已安装的 hook 定义。直接运行 hook 的测试不能证明宿主已经
信任它。Python、依赖包和本地观察数据保留在本机。

Windows 自动输出桥接是可选功能，需要另行验证原生宿主；安装器不会自动启用。在解压目录中
可以使用以下命令暂存并启用桥接：

```powershell
$env:CODEX_OPS_BRIDGE_PYTHON = (Resolve-Path ./plugin/.venv/Scripts/python.exe).Path
& $env:CODEX_OPS_BRIDGE_PYTHON ./plugin/runtime_bridge/control.py stage
& $env:CODEX_OPS_BRIDGE_PYTHON ./plugin/runtime_bridge/control.py enable
```

同版本的已有运行时不会被覆盖；内容不一致时暂存操作会报错。重启桌面程序后再检查桥接状态。
Linux 和 macOS 的自动输出桥接、分阶段目录创建与删除目前尚不可用。此预览版不代表各平台
功能完全一致。
