# 外层输出自动压缩原型

这里记录最初的隔离 stdio 原型；0.2.0 在此基础上实现了
[桌面 gRPC 运行时桥接](../runtime_bridge/README.md)。
英文说明见 [README](README.md)。

## 已验证

不修改本机 `codex-code-mode-host.exe`，在独立进程中只压缩其发出的呈现消息，
工具返回值通道逐字节转发。测试脚本只使用正常的 `text(r)`、`notify(r)`、
`yield_control()`，没有调用 ops_capture，也没有替换脚本中的辅助函数。
输出后仍能检查完整 200 条记录、中文、false 和 null，保存的引用能重建原始输出文字。

| 场景 | 原始 UTF-8 字节 | 经适配器后 |
|---|---:|---:|
| text | 100,148 | 3,953 |
| notify | 100,148 | 3,953 |
| yield、wait 与 notify | 300,424 | 11,839 |
| 脚本报错 | 100,138 | 100,138 |
| 缓存不可用 | 100,148 | 100,148 |

10 次基线/适配器执行通过，另有 7 项单元测试覆盖媒体顺序、控制消息、工具数据、错误、
未知消息及元数据。媒体仅做了协议数据测试，没有宣称桌面视觉端到端通过。这些是字节数，
不是 token 节省率。证据在 `../verification/code-host-report.json`，含宿主文件 SHA-256
和各次隔离运行的消息记录路径。

## 为什么需要独立运行时入口

在当前 Codex 0.165.0-alpha.1.2 中，全匹配的 PreToolUse/PostToolUse 没有收到
外层 exec 的 text、notify、yield 或 wait 事件；嵌套 MCP 对照用例会触发它们。
每次 exec 都创建新的 V8 isolate，因此执行一次 JavaScript 初始化也不能接管之后的调用。

官方配置说明有 code mode 启用和工具路由选项，没有插件初始化脚本或输出转换回调。
官方开发命令提供 app-server 的 `--code-mode-host` 入口，但本机版本拒绝文档示例
中的 ws:// 地址，要求 http:// 或 https://；随附 host 则提供 stdio 与 gRPC listener。
因此不能直接把文档里的 WebSocket 例子当作本机已经验证的安装方案。

后续的 gRPC 适配器与原生 CLI 启动器实现了桌面连接；插件 manifest 本身不能选择
远程 host。下面的 stdio 原型保留作为隔离测试，生产入口位于 `runtime_bridge`。

## 代码边界

- `code_mode_bridge.py` 启动自有的原生 host 子进程，转发带长度前缀的 JSON stdio
  协议。入站工具结果、代码和取消消息保持逐字节不变。
- `presentation.py` 只处理初次执行结果、wait 返回和 notification/send 中的文字。
  调用 ID、cell ID、计时、控制信息和非文字媒体保留。
- 脚本失败时保留缓冲的诊断输出；失败之前已经发送的 notify 可能已有引用，后续错误
  本身不会改写。缓存失败或未知格式原样返回。
- 引用保存的是已经发出的文字，使用 ops_result 的 raw 视图取回；不是脚本内部对象，
  也无法找回宿主在呈现前已截掉的字节。
- REA 工具/CLI 当前不可用；这里的证据来自自有本地进程和 IPC 实验，不冒充反编译
  或 REA Evidence。

在 dsh-ops 目录运行：

```console
python -m unittest discover -s packages/codex-ops/tests -p test_presentation.py -v
python packages/codex-ops/tests/run_code_host_tests.py
```

桥接入口 `experimental/code_mode_bridge.py --upstream 宿主exe路径` 是二进制 stdio
传输，不是聊天工具；使用 Python 标准库与现有结果存储，无需安装新依赖。

官方来源：[Hooks](https://learn.chatgpt.com/docs/hooks)、
[配置](https://learn.chatgpt.com/docs/config-file/config-reference)、
[开发命令](https://learn.chatgpt.com/docs/developer-commands)。
