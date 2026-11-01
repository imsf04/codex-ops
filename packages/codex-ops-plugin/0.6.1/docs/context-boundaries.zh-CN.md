# 上下文证据与重复输出

Codex Ops 会在同一个 Execute 或 Wait 返回帧内复用完全相同文字的引用。首次压缩
预览和重复回执随同一返回到达；重复回执标明首次文字块，并保留其原文引用和元数据。
记录只活到当前返回结束，最多 16 条、2 MiB 原文字节。通知流和此前返回不会复用。
程序内部值、入站协议帧、媒体和原生错误状态保持不变。

这还不是跨模型步骤的上下文感知文件读取去重。当前 Codex 0.165.0-alpha.1.2 的
`thread/read` 返回历史记录；生成的 schema 明确把 `includeTurns` 描述为历史加载。
`thread/compacted` 及替代它的 `ContextCompaction` 项提供压缩事件，但没有给出
当前模型请求实际包含的消息正文。`thread/sample` 会发起模型采样，返回文字和用量，
不提供权威的当前上下文正文。原生 Code Mode 桥接观察工具执行，不观察提示组装。
因此文件未改变、缓存命中、历史 transcript 或 window ID 都不足以省略跨请求正文。
该优化仍未启用，也没有安装等待信号的虚假去重引擎。

## 归因标识

已在本机宿主验证：同一聊天两次执行、同一 app-server 两个聊天、yield 后 Wait，
以及原生嵌套 MCP 调用。

- Execute 字段 1 是原生 Code Mode 会话 UUID；实测同一聊天重复执行保持一致，
  两个聊天不同，Wait 字段 1 与其对应。统计标为 `code-mode:<uuid>`，不冒充聊天 ID。
- Execute 字段 2 每次调用变化；Wait 字段 2 是 cell ID，都不能当作稳定会话标识。
  通知请求缺少已验证的会话身份，因此只按工具归因。
- MCP 请求元数据包含 `threadId`、`windowId`、`itemId` 和
  `x-codex-turn-metadata.thread_id`。实测 thread ID 与独立 app-server 的聊天启动
  事件相符；身份冲突时不归因。有效身份标为 `chat:<threadId>`，不保留命令或正文。
- MCP 元数据通过注入的 `mcp.server.mcpserver.Context` 获取，实际类型为字典，
  不从工具参数取值。其中的沙箱字段不会被当作脱离宿主权限执行写操作的授权。

`bridge_context.py` 只提取有界、针对当前版本验证过的统计身份。信号缺失、损坏或
未知时，保留会话归因缺失。这些标识不证明当前提示包含什么，也不会自动形成引用 ACL。

## 验证依据

本机执行 `codex app-server generate-json-schema --experimental --out <目录>`
生成协议说明。原生 gRPC reflection 返回 `UNIMPLEMENTED`，因此上述字段解释来自
实际运行的隔离探针，而非猜测描述符。`verification/context-evidence/` 保留帧验证、
MCP 元数据、身份对照和覆盖率结果。探针使用固定响应的本地模型服务器，不代表真实
模型质量或 token 节省。

English: [Context evidence and repetition](context-boundaries.md).
