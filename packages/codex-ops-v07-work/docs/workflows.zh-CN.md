# 只读工作流

`ops_workflow(root, operation, args)` 将产生证据的读取组合起来。`root` 必须是现有绝对目录。
原生 worker 继续拒绝越界、链接、凭据路径和不支持的格式。工作流不执行 shell 命令，
不授予修改权限；须检查各阶段的状态和覆盖范围。

| 操作 | 参数 | 返回 |
| --- | --- | --- |
| `locate` | 原 `ops_files(search)` 参数 | 匹配、合并的上下文范围、重新读取后的匹配检查。 |
| `diagnose` | `logPath`、`log`、`logRef` 三选一；可选 `maxLocations`、`maxEvidence`、`before`、`after` | 诊断行和有界原生源代码读取。 |
| `documents` | `requests:[{operation,args}]`，可选字面 `query`、`maxEvidence` | 小结果直接返回，大结果保留选中证据和完整引用。 |
| `incremental` | `files:[{path,offset?,limit?}]`，可选 `baselineRef` | 首次完整范围，随后对明确保存的基线生成范围差异。 |
| `sdk` | `{}` | 可执行 JavaScript 客户端工厂与 TypeScript 声明。 |

日志文件可直接用 `{logPath:"build.log"}`：原生 stat 拒绝目录，原生 grep 优先选取失败证据，
保留原始行号及 `logSource` 的扫描/分页覆盖。`logLinesScanned=null`，因为 grep 不报告总日志行数。
空匹配或有界扫描不证明整个日志成功；文件仍须位于指定 root 内。

直接传入文本时最多接受 256 KiB UTF-8 日志。日志引用必须指向字符串或带字符串 `output` 的 shell
结果；它是已有观察，不是重新执行。支持 Python traceback、`file:line`、Node 的具名或
无函数名堆栈、Rust `--> file:line:column`，以及 TypeScript
`file(line,column)` 位置。最多选取 16 个位置与 40 条诊断，并报告省略量。根目录外的位置
只计数、不读取；文件缺失或权限拒绝保留原生错误。启发式解析不能证明找出了全部失败。
自动捕获 `text(shellResult)` 得到的有界 JSON shell 信封会先解码，再按行解析，也支持
已知 MCP 文字包装。仅有 `output` 字段、没有 shell 标识的任意 JSON 字符串仍按原文处理。
也识别精确的 `{status:"fulfilled",value:<shell结果>}` 包装。额度不足时优先保留错误，再保留
警告和成功摘要；最终按原行号展示。

文档工作流接受 1–4 个原生 `read`、`read_table`、`read_docx`、`read_pdf` 或 `inspect` 请求。
参数沿用原操作，可通过 `ops_catalog` 查询。非空字面搜索每个返回结果最多遍历 4,000 个节点，
每个请求最多返回 40 项证据。小原生结果放入 `item.result`，全组共享 4,096 字节预算，原始覆盖
和游标就在其中；证据只给指针，不重复正文。大结果保存为 `resultRef`，附 `sourceCoverage`。
匹配表格单元格会返回完整行和列名；行超过 800 字节才保留明确标注裁剪的片段。空查询不扫描
元数据或复制内容。需要读最多 1,000 行时显式给 `limit:1000`；查询不会扫描尚未读取的源页。
`scanComplete` 仅描述返回的原生结果，不代表原文档完整；`sourceComplete` 保留源完整性。
源内容或证据扫描不完整时，零匹配返回 `matchConclusion: "unknown"`，不证明内容不存在。
直接使用已经返回的内容，只有缺少证据时才取 `resultRef`；遗漏的原文页需使用源结果的续读游标。

增量读取接受 1–8 个范围，每个 1–300 行；每次都会实际读取当前范围。基线必须属于同一
可信会话、根目录及完全相同的范围请求。`snapshotRef` 的 `/result` 保存完整当前原生结果，
`baselineRef` 标明比较输入。只有调用者明确要求比较时才省略未变化行，不假设模型上下文
仍保留它们。全文件版本变化但范围差异为空，仅表示所选窗口相同，不表示全文件没变。
基线过期或不可访问会在重新读取前失败；应显式开始新基线。

Code Mode 可请求 `sdk`；若返回引用，先取回 `/javascript` 字段。在 `functions.exec` 中
执行返回的 `createOps` 声明，再调用
`createOps(tools, ALL_TOOLS, root)`。工厂自动发现唯一 `ops_workflow` 工具，保留账户前缀，
调用真实 MCP 操作。调用会解开 inline 回执，大结果仍保留 reference 回执，不自动回读。
显式 `ops.resolve(result, maxBytes=65536)` 会发现真实 `ops_result` 名称，逐页读取并恢复
完整工作流结果。预算按恢复内容的 UTF-8 字节计，范围为 512 字节至 1 MiB，最多 256 页。
分页信封也需要空间，剩余预算不足 512 字节时拒绝继续取页。引用过期、权限拒绝或预算
不足会抛错；原引用仍可用于选择性读取，不重新执行生产操作。
客户端不注册、隐藏或替换宿主工具。真实原生 V8
host 与 Rust worker 已覆盖工厂及四种操作；这不代表支持原生动态 SDK 注册。

```javascript
const ops = createOps(tools, ALL_TOOLS, "C:/project");
const result = await ops.diagnose({logRef: "ops://...", maxLocations: 4});
text(result);
// 只有需要完整证据时才显式回读：
const full = await ops.resolve(result, 65536);
text(full.diagnostics);
```

SDK 额外提供显式 `runAndDiagnose(execArgs, diagnosticArgs={})`，将调用者指定的
`tools.exec_command` 与已完成失败的诊断组合起来。JavaScript 内部保留完整 shell 返回值。
运行中的 session 立即返回，供原生轮询继续处理；成功命令不额外诊断。超过 256 KiB 的
日志返回明确的跳过原因，由调用者选择有界日志片段。MCP 不执行 shell，不改写或重放
命令；权限检查和执行异常仍由原生工具处理。

```javascript
const run = await ops.runAndDiagnose({cmd: "python -m unittest", yield_time_ms: 1000});
text(run); // 检查 state、shell.session_id、shell.exit_code 和可选 diagnosis。
```

大型工作流回执保留有界的诊断、文档或差异证据，完整结果及原生错误仍可取回。
判断完整性前须检查省略量。

已经自包含的诊断/文档输出（包含单个 JSON MCP 信封）不超过 8 KiB 时保留原始展示文本，
避免仅因 JSON 大小再次变成引用。仅识别含实际内容、无错误的已知结构；整帧共享预算仍可
收紧输出，错误、多模态和未知结构沿用原处理。程序内部完整返回值不变。

运行时发现会先过滤过期/停止的祖先记录，再选择最近的有效 bridge，防止旧 PID 记录遮蔽
真实祖先、导致自动引用无法回读。运行时/聊天所有权规则保持原样。真实原生故障注入中，
旧查找方式失败，修正后能分四页精确重建 52,000 字节。
