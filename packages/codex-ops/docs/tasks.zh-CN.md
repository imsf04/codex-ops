# 分阶段原生任务

Codex Ops 可以先规划分阶段的文件和目录修改，不写入工作区。保存的计划包含完整序列
和已观察到的文件版本。实际执行使用返回的 argv，通过 Codex 原生 shell 和现有权限。
MCP 规划不授予执行权限，也不启动工作进程或额外调度器。

`task_api.plan(root, stages, owner=None)` 接收已存在的绝对根目录及 1–16 个有序阶段。
每阶段有 1–32 个 `{operation, args}`；总计最多 64 个请求操作，展开后最多 256 个步骤。
所有操作按输入顺序执行，同一阶段内也一样；后续操作可以依赖前面的结果。阶段用于
检查和恢复，并非原子文件系统事务。

六类文件操作保留已有参数：`write`、`edit`、`replace`、`copy`、`move`、`remove`。
新增目录操作：

| 操作 | 参数 | 前提 |
| --- | --- | --- |
| `mkdir` | `{path}` | 执行至此时父目录存在，目标不存在。 |
| `rmdir` | `{path}` | 目标为空目录。 |
| `copy_tree` | `{path, to}` | 指定源目录；目标不存在，源与目标不重叠。 |
| `move_tree` | `{path, to}` | 校验复制后再删除，不是原子重命名。 |
| `remove_tree` | `{path}` | 指定源目录，检查已捕获的全部后代。 |

路径为根目录内的规范相对路径。拒绝根目录本身、向上越界、链接/reparse point、硬链接
文件、凭据、日志目录、备用数据流、设备名和有歧义的 Windows 路径。同一 Windows 路径
必须使用相同大小写拼写。目录树最多 128 个节点，每文件最多 1 MiB，总内容最多 8 MiB。
目录操作不承诺保留目录所有者、ACL 或时间戳；回滚恢复所观察的目录结构和文件内容。
文件 worker 继续执行原版元数据检查；写入字节后仍可能返回权限或元数据失败。

阶段示例：

```json
[
  [{"operation":"mkdir","args":{"path":"review"}}],
  [{"operation":"copy","args":{"path":"src/a.txt","to":"review/a.txt"}}],
  [{"operation":"replace","args":{"path":"review/a.txt","oldText":"old","newText":"new","expectedCount":1}}]
]
```

原生命令入口为 `mutations/task_cli.py`：

```text
apply --plan-ref ops://…
status --root ABSOLUTE_ROOT --id TASK_ID
cancel --root ABSOLUTE_ROOT --id TASK_ID
resume --root ABSOLUTE_ROOT --id TASK_ID
rollback --root ABSOLUTE_ROOT --id TASK_ID
```

`apply` 在产生文件修改前输出包含任务 ID 的 `started` 记录，结束后输出最终回执。
进程仍运行时保留原生 shell session ID。`cancel` 请求在下一个步骤前停止，不终止正在
运行的 worker；需要立即终止时使用原生进程控制。显式 `resume` 会清除取消请求。
回滚按逆序执行；出现意外文件或外部内容修改时会拒绝继续。

任务日志位于 `.codex-ops-tasks`，文件步骤仍使用各自的 `.codex-ops-mutations` 恢复日志。
父任务在文件修改前保存子日志 ID，每一步执行前校验当前目录树状态。进程中断后，status
会说明记录位置是否匹配当前文件；显式恢复能识别已完成但未记录进度的一步，并避免重放。
未知或部分修改会停在 `needs-inspection`，提供当前子日志 ID。结果不确定时不要再次 apply；
先检查子日志和现有文件，再选择显式续做或回滚。

若受跟踪的子步骤在移动途中停止，显式恢复会先核对子计划和其他未涉及路径，再调用
该子日志的恢复能力。目标已复制、源尚未删除的状态可以选择续做或回滚。恢复方向在
产生修改前持久化；恢复过程中再次中断，仍可继续回滚，不会重新转为正向执行。
子文件内容冲突或其他已捕获路径发生变化时，仍拒绝继续并要求检查。

面板在同一总字节和条目限制内展示两类日志，只显示日志阶段和数量，不重新验证文件状态。
需要检查当前后置条件时调用原生 status。显式 root/task ID 用于定位工作区日志，本身不构成
独立的聊天间文件系统授权。

## 各平台的目录授权

Windows 在每次目录原语期间持有父目录句柄，阻止重命名和 reparse 替换。
Linux 和 macOS 使用已打开目录的身份授权：逐级相对打开目录并设置 `O_DIRECTORY | O_NOFOLLOW`，
通过父目录句柄执行创建与删除。并发重命名可能把已授权目录移动到原路径之外；操作仍作用于该目录
身份，原路径上的替换符号链接无法重定向操作。这是明确批准的 POSIX 契约，不承诺阻止其他进程
重命名目录；最终路径分量也不会跟随符号链接。
任务仍执行边界状态与修订检查。如果路径变化使后续观察或恢复失败，应检查日志及实际位置；
错误不表示之前没有产生效果。
