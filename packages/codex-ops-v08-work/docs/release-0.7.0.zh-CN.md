# Codex Ops 0.7.0 候选验收

日期：2026-10-30。功能实现和验收已完成。冻结成本目标未全部达到，
releaseGatePassed 保持 false；用户明确选择“先启用当前 0.7.0，保留未达标记录和回退”。
该决定单独记录为experimentalAcceptance，不将FAIL/UNKNOWN改为PASS。

## 已实现

- investigate：问题、可选字面锚点与路径，组合有界搜索和源码上下文；返回证据、覆盖与缺口，不伪称语义答案。
- 统一证据呈现：investigate/evidence/working_set/verify 的已识别有界结果直返；长验证失败直接显示退出状态和诊断，原始观察可精确取回。
- 跨引用检索：使用现有 Python 的 SQLite FTS5，对当前仍获授权的 1–8 个观察值做字面检索。每次重新授权，不新增网络服务。
- 原生验证：SDK verifyRun 经 exec_command/write_stdin 执行和有界轮询；MCP verify 仅分析已观察结果。
- 工作集：保存同 chat/root 的来源清单与待核验项；恢复重验权限、TTL 和文件修订，不恢复过期授权，不修改历史上下文。
- 实耗与预算：按真实聊天读取 usage，分开记录缓存/未缓存、外层/原生动作；同聊天即时补读只作为预算增加的代理信号。

没有复制第三方项目代码或增加依赖。复用已有 native adapter/store/task/SDK 和
Python 内置 SQLite FTS5；开发、生产环境均实际验证 FTS5 可用。
详见 [来源](open-source-0.7.0.md) 与 [接口](workflows-0.7.0.md)。

## 确定性验收

完整质量检查通过459项测试、8项app-server对照、3项启动器插桩检查。
83个Python生产/安装模块、797个函数，CRAP最高6、超过6为0，
语句与分支合并覆盖率99.25%。Rust shim未变，不将Python CRAP覆盖结论外推到Rust/嵌入式JS。

暂存运行时15项真实native检查通过。强化场景保留20,863字符/320行日志，
最后ERROR和exitCode=2直接可见，外层引用包装为0；原生命令执行1次、轮询1次，
观察原文经7页取回与程序内值结构相同。

首次native新建文件的ACL失败保留；后续测试明确使用host预建源文件、native修改。
没有改权限，也没有把这个输入权限边界算作已修复。

## 真实模型比较

同一 gpt-6.1-terra / medium，12个任务、每组3次，共72个可比较结果。
使用各版本真实skill和SessionStart文案作为开发者指导；没有在任务里强制调用插件，
但skill是提前完整注入，不能等同日常按需加载。原生命令仍使用workspace-write配置。

| 指标 | 0.6.1 | 0.7.0 |
| --- | ---: | ---: |
| 严格成功 | 29/36 | 34/36 |
| 全部尝试原生动作 | 273 | 205 |
| 全部累计输入token（含缓存） | 8,187,681 | 6,326,924 |
| 全部未缓存输入token | 831,393 | 740,748 |
| 28个共同成功配对原生动作 | 197 | 159 |
| 共同成功累计输入token | 5,999,077 | 5,036,759 |
| 共同成功未缓存输入token | 639,205 | 594,007 |

全部尝试原生动作减少24.91%、输入减少22.73%、未缓存输入减少10.90%。
冻结目标按共同成功配对判定：动作减少19.29%（目标25%，FAIL）、
输入减少16.04%（目标20%，FAIL）；未缓存输入不增为PASS。
展示诱发补读减少50%保持UNKNOWN，不能用总取回次数代替。

本机原生experimentalRawEvents经无付费协议探测证明可精确观察外层调用，
并仅为后续未启动配对启用。相同可观察集合的30对：exec285→214（-24.91%）；
其中23对共同成功：207→166（-19.81%）。初始12条缺测保留unavailable，
不是0；oracle验收活动排除。原生动作不包括MCP内部worker启动数，不能称全系统操作总数。

## 采用情况

含工作流调用的任务数23/36→21/36，并没有上升。候选实际调用：
investigate21次、documents4次、diagnose3次。没有将未用的新功能算作自然采用；
evidence/working_set/verify 的功能覆盖来自确定性与native验收。
任务没有独立的“符合条件机会”标注，naturalAdoptionRate保持null。
新调查入口已被真实模型选择，但不能宣称六项都已成为日常习惯。

候选3次ops_result：1次来自错误docx读取后的取回，因早期缺raw呈现因果未知；
1次是完整skill读取与目录失败混合结果，因果仍未知；1次确认是partial documents
预览隐藏已存在的文件状态及ACCESS_DENIED，导致额外取回。
基线唯一取回亦缺raw证据，故不能证明展示补读减少50%。

## 失败与可比性

两条候选严格失败都是长任务。一次请求了正确workdir但实际在C盘查找脚本，
并遭遇访问拒绝；另一次有正确答案/receipt但缺冻结规则要求的原生终态7。
后者对应唯一基线成功、候选失败的配对。两次都未采用SDK或工作流。
未定位工作目录问题属于native host、PowerShell还是沙箱的哪一层，不能称已解决。
其他失败原样保留，样本成功数提升不构成一般质量等价或长期稳定性保证。

第一个候选因verify长失败预览缺诊断而停止，9条完成+1条中断及源代码/bundle留存。
修复后的原始比较还发现fixture用write_text在Windows生成CRLF，却要求LF。
原生执行证明该生成器与原约定冲突；仅改独立生成适配器为write_bytes，
不改答案、oracle或阈值。原2条长任务FAIL保留并计入开发消耗。
组合72条明确来自26条非长任务复用和46条续测，逐条记录来源SHA/key；
不是一次未修改的完整运行，也没有把旧FAIL替换成PASS。

开发全部已知消耗下界：输入16,594,497、总token16,690,480，含原invalid两条
及首轮中断已知用量；中断在途未报告部分仍未知。该数不等于账单金额。

## 交付状态与证据

验证源码目录：packages/codex-ops-v07-work。部署将保留0.6.1源码、配置和运行时回退，
通过原生插件安装与CLI override选择0.7.0；桌面端须重启加载新进程。
具体安装状态以verification/desktop-installation.json为准。
性能目标及未达状态仍保留：[冻结验收](../verification/v070-acceptance-design.json)。

- [安全成本摘要与启用决定](../verification/v070-cost-summary.json)
- [原生验收](../verification/v070-native-final-summary.json)
- [源码质量](../verification/quality/crap.json)
- [失败审计](../verification/v070-final-failure-audit.json)
- [采用及调用审计](../verification/v070-combined-tool-audit-final.json)
- [取回证据标注](../verification/v070-retrieval-annotations.json)

