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

Linux 和 macOS 安装程序还会准备 `plugin/bin/codex-ops-cli`。如需试用，将
`CODEX_OPS_REAL_CLI` 设置为原生 Codex 可执行文件；同一目录必须包含
`codex-code-mode-host`，然后将启动 `app-server` 的宿主配置为使用该启动器。压缩仅针对已验证的
Codex CLI 0.165.0-alpha.1 的 Linux x64、macOS ARM64 和 macOS x64 宿主哈希启用；未验证的
原生宿主输出会原样转发。设置 HTTP 代理时会回退到原生输出。

直接启动 app-server 会话：

```sh
CODEX_OPS_REAL_CLI=/absolute/path/to/codex ./plugin/bin/codex-ops-cli app-server --stdio
```

对于支持 `CODEX_CLI_PATH` 的宿主，在其启动环境中将该变量设为启动器的绝对路径，同时设置
`CODEX_OPS_REAL_CLI`。完全重启宿主使环境生效；`ops_stats` 会报告当前进程是否实际接入桥接。
无图形界面的 CI 尚未验证桌面 GUI 启用过程及更多宿主版本。

CI 在隔离的 Codex home 中安装搬移后的插件包，通过真实宿主信任并执行 hook，并经打包启动器
验证文本、异步输出、错误、图片、工具错误、MCP 值和实际桥接状态。还会执行安装后的目录任务
与回滚、Python 全量测试及 Rust 测试；平台专属跳过单独报告。

Linux 和 macOS 目录任务以已打开目录的身份为授权边界：逐级打开目录并拒绝符号链接，
通过父目录句柄创建或删除子目录。外部重命名可能移动该目录，操作仍作用于已授权的原目录，
不会被替换路径上的符号链接引向其他目标。Windows 则在目录操作期间阻止父目录重命名。
详见[任务契约](tasks.zh-CN.md)。
