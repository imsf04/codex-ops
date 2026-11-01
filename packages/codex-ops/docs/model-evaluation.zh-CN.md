# 0.6 受控模型评测

评测包含二十个实例：代码定位、修复、批量修改、日志诊断、文档查询各四个；每个重复两次，
三个条件共计划 120 次。固定实际配置模型、原生 workspace-write 沙箱以及普通权限的工作区/
缓存布局。原生与冻结的 0.5 先运行，0.6 在暂存和源码验证后加入，因此不能声称三个条件从
一开始完全交错。保留实际时间戳；最多并行两个独立 app-server，系统负载和缓存顺序会影响耗时。

原生条件没有 OPS 指引；启用条件通过原生 `developerInstructions` 接收对应版本真实 skill 和
活动 SessionStart 文本，并加载 MCP 工具及桥接。这验证等效指引，不代表执行了 hooks。
本评测没有运行真正的 DSH 宿主，不能证明跨宿主优势。
每个启用组实例都提前注入完整 skill，未复现日常按需加载，也未执行真正的 PostToolUse
hook；这些小任务上的额外指引/schema 开销属于本次测量条件。

每个实例都拒绝未完成状态，并通过独立标准答案。可信校验器在相同原生沙箱中执行，其代码
位于模型可编辑实例之外。检查原始输入哈希、精确输出文件、字段类型、隐藏修复用例，以及
输入不被修改、返回容器不与输入共享。

最初校验器对部分未限定形式的标签过于严格。原始结果全部保留，只重新校验现有文件，不重跑
模型。冻结的 `v06.3-frozen-semantics` 接受以下等价表达：

- 源代码路径可使用两种斜线和实例绝对前缀，实际源文件/测试文件及定义行、证据行必须一致。
- 授权 `override` 接受 `suspended`、`suspension`、`suspended flag`、`suspended status`、
  `suspension overrides ownership`。
- 舍入接受 `half-up`、`half up`、`round half up`、`half-up rounding`、`half_up`。
- 迁移根因接受 `SCHEMA_VERSION` 或 `schema_version_mismatch` / `schema version mismatch`。
- trace 的 `downstream` 接受错误码 `ORDER_ABORTED` 或其真实服务 `orders`；题目未限定二者，
  其它服务仍失败。
- 编译根因接受 `TS2322` 或这个精确代码后接冒号解释。观察类型接受 `string` 或
  `source.age is [the] string "42".`，也允许单引号及末尾无句号。期望类型接受 `number`
  或以 `User.age must be a number, parsed as an integer at the import boundary` 开头的描述。

其它内容保持精确，包括词法标识符、整数/布尔类型、金额、文件身份和行号。负面对照逐个破坏
每个答案字段；错误路径、行、类型、错误身份必须失败。记录最终校验源码哈希，后续不再按模型
输出增加别名，也不重跑付费尝试。

效率百分比只计算成功且环境可比的配对，所有失败、超时或受阻尝试仍进入结果与成功数。
总/input token 包含重复缓存上下文，另报非缓存输入，但不当作账单。原生已完成 command/MCP/
file-change 事件仅作为明确的工作项代理，不声称覆盖全部嵌套 JavaScript 工具调用。
二十个相关任务实例不能证明统计显著或普遍优势。
