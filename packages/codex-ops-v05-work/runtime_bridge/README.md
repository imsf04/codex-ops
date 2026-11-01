# Windows Desktop runtime / Windows 桌面运行时

Codex Ops 0.5.0 uses the installed Desktop's `CODEX_CLI_PATH` executable override.
The native shim forwards ordinary CLI commands unchanged. For app-server service
starts it owns an unmodified native Code Mode host, a loopback gRPC presentation
relay, and the real app-server with `--code-mode-host http://127.0.0.1:PORT`.
It does not patch OpenAI executables, inject JavaScript into Desktop, or proxy model APIs.

0.5.0 使用当前桌面程序支持的 `CODEX_CLI_PATH` 可执行文件覆盖入口。普通 CLI 命令
保持原样；启动 app-server 时，启动器管理原生 host、回环 gRPC 呈现适配器与真实
app-server，通过 `--code-mode-host` 连接。OpenAI 二进制和模型 API 不作修改。

## Boundary / 边界

- All client-to-host protobuf messages, including CompleteToolCall values, source,
  control and IDs, are forwarded byte-for-byte. Only known outbound text fields in
  Execute, Wait and OpenSession notifications can change. Media and unknown fields
  remain opaque. The host keeps full tool values inside JavaScript.
- Successful, yielded and failed-buffer text over the presentation threshold can
  become a preview and `ops://` reference. Native error state/diagnostics remain
  unchanged. Notifications already emitted
  before a later failure can already be compacted; the later error stays intact.
- References preserve emitted UTF-8 text, not an internal typed object. Use
  `ops_result(ref, view="raw")`, following nextOffset. Host truncation before emission
  cannot be recovered. Cache size, quota and TTL are shared with the plugin.
- A host SHA not in `validated-host.json` disables transformation and forwards raw
  messages. Unknown schemas and unavailable storage pass through. Bridge startup
  failures fall back to the native host. A crash after a live session starts requires
  an app-server restart; there is no mid-session migration to another host.
- Windows Job Objects terminate owned descendants even when Desktop kills only the
  shim. Failed Job assignment prevents service startup. No unrelated processes are killed.
- The Desktop override removes its contained-core package identity by design. The
  Windows workspace-write/elevated sandbox was tested with this exact behavior;
  sandbox settings and authentication are not weakened or replaced.

入站工具值、代码和控制消息逐字节转发；只改变已验证的出站文字字段，媒体及未知字段
保持原样。失败保留原生诊断，大段缓冲日志可生成引用；缓存失败保留原文，未知 host
版本停止压缩。已发出的 notify
可能在脚本随后失败前就被压缩。引用保存的是发出的文字，不是程序内部对象。
启动失败可退回原生 host；运行中桥接崩溃需要重启后端，不支持热迁移。
Windows Job Object 只清理启动器拥有的子进程。使用覆盖入口后桌面程序会移除原有
contained-core 身份；已按这一实际路径验证现有 Windows 沙箱配置，未降低沙箱策略。

## Install and inspect / 安装与检查

Run from the package directory with the pinned bridge Python environment:

```powershell
$bridgePython = "$env:USERPROFILE\.local\share\codex-runtimes\codex-ops-uv\Scripts\python.exe"
& $bridgePython runtime_bridge/control.py stage
# Verify the staged executable through tests/probe_app_server.py --shim --shim-path PATH.
& $bridgePython runtime_bridge/control.py enable
& $bridgePython runtime_bridge/control.py status
```

`stage` copies the exact runtime and hashes into `%LOCALAPPDATA%/CodexOps/runtime/0.5.0`.
`enable` verifies those hashes, saves the previous user override and changes only
`HKCU\Environment\CODEX_CLI_PATH`, then broadcasts the environment change. Install
the matching native plugin with `codex plugin add codex-ops@personal --json`.
Hook trust remains a separate host mechanism. The user's authorization governs updates.

**Fully quit and reopen Desktop.** Restarting only app-server, opening another window,
or launching a second instance cannot refresh the existing main process environment.
`control.py launch` starts the packaged Desktop with the configured value explicitly;
it does not terminate an existing Desktop. Normal new Desktop launches inherit the
user environment. A running instance still uses its original executable until quit.

`stage` 将运行时复制到独立版本目录并记录哈希；`enable` 保存此前用户环境值，只设置
`CODEX_CLI_PATH`。安装匹配插件后，需要**完整退出并重新打开桌面程序**。
重启后端、开新窗口或启动第二个实例都不会刷新旧主进程环境。`launch` 可明确传入
新配置启动桌面程序，但不会强制终止正在运行的实例。

Verify `ops_stats.runtimeBridge.activeForThisProcess == true`. Status checks the
native process identity/ancestry and fresh instance metadata, not the existence of
some unrelated bridge. Then ordinary `text(result)` / `notify(result)` works without
`ops_capture`. A successful fixture must show an ops reference, retain the in-script
raw-value assertion, and increment that bridge's compactedFrames counter.

确认 `ops_stats.runtimeBridge.activeForThisProcess` 为 true 后，直接使用 text/notify。
状态检查当前进程身份和新鲜的实例记录，不把其他进程的桥接误认为本聊天已接入。

## Rollback / 回退

```powershell
& $bridgePython runtime_bridge/control.py rollback
# Fully quit and reopen Desktop after restoring the environment.
```

Rollback restores the exact previous user value/type and leaves cached observations
and versioned runtime files intact. It refuses to overwrite an override changed by
another action. Removing the plugin alone does not remove the Desktop CLI override;
roll back the runtime first. CLI/host updates need protocol revalidation and a new
runtime version when the tested bundle changes.

回退恢复之前的用户变量值和类型，缓存与版本目录保留；若覆盖入口被另外修改，不会
覆盖新设置。仅卸载插件不会移除桌面 CLI 覆盖，因此先回退运行时，再卸载插件。

## Evidence / 验证

`verification/app-server-grpc-report.json` records actual app-server/native gRPC
round trips with a deterministic localhost model; no external model calls are made.
`verification/desktop-runtime-report.json` records staged shim checks. These are
UTF-8/model-visible byte measurements, not token or task-quality claims. Desktop
activation is recorded separately from isolated protocol validation.

Version 0.2.1 additionally tests the production status directory under MSIX path
redirection. A same-directory rename can return WinError 17 there; status publication
then uses a direct write. Readers ignore partial JSON until the next refresh.
0.2.1 额外在 MSIX 重定向下的实际状态目录验证；同目录重命名若返回 WinError 17，
改用直接写入，读取端遇到未完成的 JSON 会等待后续刷新，不影响原始工具值。

Real baseline versus bridge measurements: text 203038 → 2460 bytes, yield/wait/notify
304600 → 3733, nested MCP 139196 → 2360, buffered script error logs 20341 → 4253
while native error diagnostics remain unchanged.
Tests also cover raw values, MCP rejections, PNG output, real shell/sandbox execution,
unknown protocol, unavailable store, startup failures and process-tree cleanup.

## 0.4 attribution and repetition / 0.4 归因与重复输出

The bridge labels the verified Execute/Wait RPC and native Code Mode session. MCP
request metadata supplies a distinct chat identity. Notifications without a proven
session stay unattributed. Exact repeated text reuses its first reference only inside
one outgoing result frame; cross-model-step file deduplication remains unavailable.
See [context boundaries](../docs/context-boundaries.md).

桥接按已验证 RPC 与 Code Mode 会话归因；MCP 聊天标识是另一种身份。缺少证据时
保持未归因。同一次返回内的相同文字可以复用引用；跨模型步骤的文件去重尚不可用。
详见[上下文边界](../docs/context-boundaries.zh-CN.md)。

## 0.5 bounded semantic profiles / 0.5 有界语义摘要

Strict completed-shell test/build profiles may use small references below the generic
threshold. The replacement must preserve terminal evidence and save at least 128 bytes
and 20 percent. Other small output retains the generic thresholds. Batch retrieval and
count/group pages stay explicit retrieval. Bucketed telemetry adds recent-period evidence
without interpreting opaque protocol bytes or changing inbound values.

严格识别的已完成测试/构建输出可低于通用阈值生成小引用，必须保留终态证据，且至少
节省 128 字节与 20%。其他小输出保持原有阈值。批量检索与 count/group 页面按显式
检索处理；分桶统计提供近期证据，入站原值和不透明协议字段保持原样。
