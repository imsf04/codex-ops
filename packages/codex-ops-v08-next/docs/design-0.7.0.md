# Codex Ops 0.7.0 implementation design / 实施设计

Date: 2026-10-30. Status: designed, with read-only investigation feasibility probes.
This document does not claim implementation, benchmark gains or installation.

## Product decision / 产品决策

六个方向纳入 0.7.0，采用同一个证据接口。目标是让调用模型只提供问题与必要线索，
随后获得足以继续工作的精确内容、来源、覆盖情况和可执行的继续入口。
保留原生执行与程序内完整返回值；默认不新增模型、embedding 服务或递归 agent。
成功表现为完成任务的往返和实耗下降，工作流调用数不是独立优化目标。

All six directions share an evidence contract. The host model interprets the task;
the plugin retrieves and assembles exact evidence. No default extra model/service.

## Shared contract / 共同契约

新增操作的有界结果包含：
- operationStatus: completed / partial / failed，描述操作执行状态。
- evidenceState: collected / needs_anchor / no_match，描述取证结果，不冒充答案正确性。
- items: 精确内容与类型，source（path/ref/pointer/revision）、行/页/表格位置。
- coverage: 已检索与未检索范围、选取遗漏和源本身的完整性，分别表示。
- continuations: 可直接使用的下一步参数，仅在缺失证据时提供。
- execution: 如涉及原生验证，则包含真实退出码、session 和终态；读操作无需此字段。

旧操作保持其既有结构；先在呈现层适配旧结果，不做全量格式迁移。
共享预算适用于整个结果；未展示内容仍可精确取回。不能为节省展示改动程序内值。
必读的指令文件仍须完整遵守其阅读要求。

The packet separates execution status, evidence availability, source coverage and
selection coverage. Old operations retain their public contracts. Presentation
adapts existing results; native values remain unchanged.

## Delivery slices / 实施切片

| 切片 | 具体交付 | 复用边界 | 验收依据 |
| --- | --- | --- | --- |
| A：证据直达与实耗基线 | 统一有界工作流输出识别、避免取回再包装；记录外层/原生动作和 token | workflow_preview、query_preview、workflow_inline、presentation_policy、telemetry | 原文/错误/媒体保持；查明每次取回和每条成本来源 |
| B：问题调查入口 | investigate(question, anchors?, paths?, focus?)；一次发现和一次受限扩展 | workflow dispatch、query_workflow、native files | 三个原型场景扩展为自动可重复用例；无关键词时不全盘乱搜 |
| C：跨来源检索 | 对已授权、已取得的内容惰性建索引；一次多来源查询 | store、result_batch、query views | 反证、过期、文件变更、权限与分页边界 |
| D：验证闭环 | 原生执行、有界轮询、最终日志诊断和源码证据 | SDK runAndDiagnose、native exec/write_stdin、diagnose | 长任务、失败退出、拒绝访问、超时均保留正确状态 |
| E：恢复工作集 | 同 chat/root 的事实、来源、待办验证；重验后生成恢复证据 | store ownership、incremental、既有 task journal | 重启、来源变化、引用过期后不展示伪造或陈旧事实 |
| F：自适应预算与自然采用 | 基于可归因的补读调整预算；机会/选择/完成/退回分开统计 | A 的账本与统一 packet | 不强制点名工具的配对试验和日常机会样本 |

这些切片是一个版本内的实现顺序，不是六套独立框架。每片先验证再合并。
A's ledger establishes measurement before adaptive policy. B tests discovery
without forcing a tool name. D keeps command execution native. E restores evidence,
not expired authority or an assumed old model context.

## Investigation exploration / 第一项探索

现有 0.6.1 的六次真实读取覆盖三个问题：
运行版本选择、raw 原文分页、过期祖先记录过滤。都定位到相关文件。
初始常量命中不足以回答问题；配置扩展出现 partial，两个扩展被包装成引用。
因此 B 需要受限二阶段取证，A 需要直接交付有用内容。

定位词与扩展由研究者手选。本探测只证明底层路径可达，并发现交付摩擦；
不证明自动自然语言解析、自然采用或 token 成本改善。
中文有代码标识符时可直接提取；缺少匹配线索时返回 needs_anchor，
并利用已取得的候选词帮助调用模型补齐，不凭空声称业务语义理解。

[Investigation design](design-v070-investigate.md)
[Probe receipt](../verification/design-v070-investigate-probe.json)

## Runtime and release / 运行与发布

实现使用独立候选目录，不编辑正在服务桌面的 live source、版本缓存或不可变 bundle。
保留当前独立 uv 环境及 native 权限路径。新 hook 内容变化依照宿主 trust 机制处理。
候选先通过源码测试、CRAP、原生协议、真实模型配对和安装后 smoke，再晋级。
尚未构建候选、未启动付费模型比较、未安装或启用 0.7.0。

Implement in a separate candidate directory; promote only verified artifacts.
Existing runtime and plugin identity remain intact during development.

## Frozen acceptance / 预先确定的验收

[Machine-readable acceptance](../verification/v070-acceptance-design.json)
固定 12 类任务、每组每类 3 次；同一模型/effort、相同任务与格式要求，
使用各版本真实路由指导作为实验变量，不在用户任务里强制使用 ops。
保留全部失败、重试和超时，报告全尝试与共同成功配对。

硬性要求：协议/原始值/权限/完整性回归通过；生产 Python 函数 CRAP ≤6；
逐项调查基线成功而候选失败的任务；不能事后修改答案判定抹掉失败。
目标：共同成功配对动作减少25%、累计输入减少20%、未缓存输入不增加、
展示引起的立即补读减少50%。这些尚未测得。目标未达到时明确记录 FAIL/UNKNOWN，
不能悄悄改变阈值宣布通过。样本不支持总体质量等价结论。

Twelve task families, three repeats per arm; retain failures. Cost targets are
unmeasured objectives, not promises. Preserve strict outcome oracles and report
all-attempt as well as matched-success results.

## Detailed component design / 组件细节

[Evidence, retrieval, verification, working set and costs](design-v070-evidence.md)
[Experience research / 中文](research-v07-experience.zh-CN.md)
[Experience research / English](research-v07-experience.md)
[Upstream primary sources](research-v07-github.md)

