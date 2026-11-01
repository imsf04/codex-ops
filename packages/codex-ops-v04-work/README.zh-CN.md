# Codex Ops 0.4.0

将 dsh-ops 的完整值与模型呈现分离接入本机 Codex，提供自动压缩、渐进检索、
原生文件读取、修改计划与回读成本统计。英文见 [README](README.md)。

## 工具与使用方式

| MCP 工具 | 用途 |
| --- | --- |
| `ops_capture` | 存档大结果并提供有界预览；Code Mode 内保留完整值。 |
| `ops_result` | 读取 `items`／精确 `raw` 分页、查看 `outline`、用 `find` 定位文本或释放引用。 |
| `ops_files` | read、inspect、grep、glob、stat、diff、CSV/TSV、DOCX、受限文字层 PDF，以及并发只读批次。 |
| `ops_plan` | 预检 1–32 项不重叠的文件修改，缓存绑定版本的计划，并返回原生执行参数。 |
| `ops_stats` | 查询缓存、当前桥接、呈现字节、来源归因与独立回读成本。 |

一份短 skill 指导选择工具。[文件契约](skills/compact-output/references/files.md)
说明参数和格式限制。只读 batch 接受 1–4 项独立请求，保持输入顺序及各项错误、
覆盖范围和续读位置。文件／搜索预览保留有用记录、源路径、版本和覆盖事实；
预览样本不代表读取了整个文件或全部搜索结果。

`ops_result(view="outline")` 展示子项 JSON 指针；`find` 用字面查询返回指针、
行号及上下文，并说明有界扫描是否完成。`items` 支持路径、字段和字面筛选。
按 `nextOffset` 续读；`complete` 只代表保存的视图，不代表完整源数据。
显式取回的有界页不会再次自动压缩。raw 偏移按 Unicode 字符计数，页面由
`max_bytes` 限制，行数参数 `limit` 不限制 raw 正文。

## 通过原生权限执行修改

`ops_plan` 只读取并缓存计划，不修改工作区文件。返回的 `nativeExecution`
包含解释器和 CLI 参数，实际执行需通过 Codex 原生 `exec_command`，沿用其
真实沙箱与审批。计划或引用不代表执行权限，MCP 不启动修改执行器。

支持 write、edit、精确数量 replace、copy、move、remove 六项操作。单文件
上限 1 MiB，计划上限 8 MiB；父目录需存在，源／目标路径不能重叠，复制和移动
的目标需不存在。执行前整批预检并保存恢复快照，再使用原版 worker 按精确版本
校验发布。整个批次不是跨文件原子事务。

失败或中断后先查看 `status`，再显式 `resume` 或 `rollback`，不能盲目重复
`apply`。恢复拒绝覆盖意外的外部变更。日志保存在根目录的
`.codex-ops-mutations/`，其中含原文件内容，直到明确清理。
恢复保证内容与存在状态，不保证恢复所有文件系统属性。
详见[修改契约](skills/compact-output/references/mutations.md)。

## 自动呈现与上下文证据

经过宿主版本验证的 Windows 桥接处理已识别的 text、notify、Execute／Wait
输出。`ops_stats.runtimeBridge.activeForThisProcess` 为 true 时，普通
`text(raw)` 即可自动压缩。JavaScript 内部完整值保持不变；未启用桥接时仍可
使用 `ops_capture`。结构化 JSON／shell 从 2 KiB 起压缩，普通文本从 8 KiB 起。
同一运行中会话的重复进度从 256 字节起可生成简短引用，终态和错误诊断保留。
所有替换必须更短，保存的原始文字可继续检索。

精确重复文本仅在同一个 Execute／Wait 返回帧内复用引用。没有启用跨模型请求
的文件读取去重：历史日志、文件版本或 window ID 都不足以证明旧正文仍在当前
提示中。见[上下文证据](docs/context-boundaries.zh-CN.md)。

直接 MCP hook 可替换呈现并保留嵌套 Promise 完整值。Bash hook 只有在有界原生
transcript 匹配能证明成功完成时才压缩；失败、运行中和无法核验的输出原样返回。
回执区分完整执行与最后一个轮询块。桥接可以压缩大段失败日志，同时保留原生
错误状态及诊断；图片和音频保持原样。插件不修改 Codex 可执行文件、不安装
模型／API 代理，也不改变全局输出预算。

## 统计、面板与存储

`presentationTotals` 持久化 UTF-8 呈现字节，按通道、原因、工具和会话散列
归类，日常与测试分账。Code Mode 身份不等于聊天 ID；经核验的 MCP 元数据可
提供另一种聊天身份。notify 缺少可证明的会话时不推断；旧版数据和来源不明的
记录保留“未归因”。同一缓存引用出现不同生产来源后也保持未归因。

成功检索的返回字节和重复有界页请求单独累计。它们随后可能被呈现，与呈现字节
存在重叠，不能直接相加或相减宣称净上下文收益。观察结果关联使用按日划分的
实例桶；30 天未活跃的实例过期，每种来源最多 128 个实例。活跃实例的累计值
不是精确的滚动 30 天时序。计数不保存命令或输出正文。

使用 `python dashboard.py --output C:/absolute/stats.html --origin production`
导出支持筛选、排序的离线统计页面。详见[面板说明](docs/dashboard.zh-CN.md)。

观察结果保存在 `%LOCALAPPDATA%/CodexOps` 的 SQLite：单条 10 MiB、逻辑配额
100 MiB、24 小时有效期，使用缓存时清理。随机引用是本机用户的持有式能力，
不提供跨聊天授权隔离；结果可能含敏感正文，不上传、不加密、不保证安全擦除。
用 `ops_result(action="release")` 释放。引用过期不能成为重复源操作副作用的
理由；保存完整也不能恢复宿主已经截断的内容。

## 安装与验证

通过 `codex plugin add codex-ops@personal --json` 安装，在 `/hooks` 审阅并
信任具体定义；运行时更新后重启桌面程序。更新源目录、升版本后重新安装，
不编辑插件缓存。绝对路径适配本机；MCP、hooks 与桥接共用锁定依赖的专属 uv
环境，测量工具放在开发环境。见[部署与回退](runtime_bridge/README.md)和
[质量说明](QUALITY.md)。

原生协议测试使用本机 Codex 0.165.0-alpha.1.2、独立临时配置和本地固定响应
服务器；固定真实工具轨迹验证输出字节与完整值。另已准备显式启用的真实模型
成对修复任务评测，报告产生前不宣称效果。测试数量以
[当前质量报告](verification/quality/crap.md)和验收记录为准。
字节减少本身不证明 token 节省、任务质量提升或完成速度变快。
