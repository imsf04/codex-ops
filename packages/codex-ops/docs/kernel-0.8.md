# Codex Ops 0.8 read kernel / 只读内核

The candidate adds a one-shot Rust executable, `bin/codex-ops-kernel.exe`, for bounded
investigations. Ordinary file operations retain the existing `dsh-ops-worker.exe`.
No upstream native source was changed and no persistent worker or MCP command executor
was introduced. The kernel path can be selected explicitly with `CODEX_OPS_KERNEL`.

候选增加一次性 Rust 可执行文件 `bin/codex-ops-kernel.exe`，用于有边界的调查。
普通文件操作保留原有 worker。上游 native 源码未修改；没有引入常驻 worker 或
MCP 命令执行器。`CODEX_OPS_KERNEL` 可以显式选择调查内核。

## Contract / 契约

- `files.run(root, "investigate", {plans:[...]})` launches one process. Each of at most
  12 plans performs native grep and, when matches exist, one merged context read.
  The original native path, credential-name, no-follow and read-only checks apply to
  every leaf request. No captured authority or mutation storage is reused.
- The result carries original source lines, file revisions, search coverage and
  match/read consistency checks. It preserves errors alongside successful stages;
  `omittedStages` and `pendingStages` expose bounded-result omissions.
- Explicit file paths never expand to siblings. Directory searches can add test or
  configuration roles when requested. Definition/reference/configuration/failure
  change the plan; this remains lexical source evidence, not a semantic call graph.
  Definition matching covers common `def`, `fn`, `function`, class/type and assignment
  declarations; absence of such syntax is reported as no match.
- Generated verification/coverage/build/dist data and minified assets are excluded
  by declared glob filters for directory searches. Explicit file targets remain
  explicit. Limits and incomplete traversal remain visible.
- Native deadline exit 124 and Python timeout/termination retain failure state.
  Python kills and reaps interrupted children. Worker events are recorded only after
  actual process creation, and parallel read batches propagate separate ContextVars.

最多 12 个计划共用一个进程；每个计划执行原生 grep，再按需要读取合并后的上下文。
逐步保留权限、凭据名隔离、不跟随链接与只读约束。源码行、修订、匹配一致性、错误、
覆盖缺口以及未执行完成的计划都可见。显式文件不会自动扩大为同级文件。
测试与配置线索、focus 参数会改变计划，但结果仍是字面检索证据，不声称完整语义图。
目录搜索声明排除生成产物；显式文件仍按调用者指定处理。超时和取消会终止并回收子进程。

## Build and validation / 构建与验证

From the candidate root / 在候选目录执行：

```powershell
cargo build --release --locked --offline --manifest-path rust-kernel/Cargo.toml
Copy-Item -LiteralPath rust-kernel/target/release/codex-ops-kernel.exe -Destination bin/codex-ops-kernel.exe
..\codex-ops\.venv\Scripts\python.exe tests/measure_v080_rust.py
..\codex-ops\.venv\Scripts\python.exe tests/profile_v080_kernel.py
```

The quality runner uses the installed Rust toolchain's matching LLVM tools, real
instrumented unit/integration tests, Lizard Rust complexity, and the lower of measured
line and code-region coverage in the CRAP formula. Stable compiler branch/MC/DC coverage
is not claimed. It measures all 40 functions written in this crate's production source;
unchanged upstream crates and the pre-existing launcher shim are explicitly outside this
new-source score, rather than being assigned the Python score.

The current receipt has 10 Rust unit tests and eight Python/native integration tests,
maximum CRAP approximately 5.0043, zero above six. Tests include actual deadline exit,
subprocess termination, path/credential denial, mixed errors, output-budget omissions,
intent-specific source selection and real parallel-batch chat attribution. The receipt
contains source hashes, the Cargo lock hash and unchanged upstream commit/file hashes.

质量脚本使用与 Rust 编译器匹配的 LLVM 实际插桩结果及 Lizard 复杂度；CRAP 取行覆盖和
代码区域覆盖两者中的较低比例。不把该结果称为分支或 MC/DC 覆盖。新内核生产代码的
40 个函数全部计分，最高约 5.0043，没有超过 6。上游依赖与已有启动器保留独立范围说明。
10 项 Rust 单元测试和 8 项 Python/原生集成测试覆盖真实超时、子进程终止、权限、输出
预算、调查意图和并行调用归因。来源、锁文件与未改动上游的哈希均记录在验收文件中。

## Measurements and sources / 测量与来源

[Rust quality](../verification/rust-quality/latest.json) and
[same-fixture timing](../verification/v080-kernel-profile.json) are local receipts.
The timing experiment counts actual Popen launches, preserves exact selected source
lines, retains all seven samples and excludes MCP/model latency and process cold start.
It demonstrates the process reduction for the measured file query, not end-to-end task
or token savings. Production Python quality and model adoption/cost acceptance remain
separate release gates.

局部计时使用相同固定文件，记录实际进程启动与全部 7 次样本，验证返回源码行准确；
不包含 MCP、模型等待与父进程冷启动，不能代替端到端成本验收。

The crate reuses the existing MIT-licensed `dsh-ops-core` and already locked serde
dependencies; [retained license](../rust-kernel/LICENSE). See
[upstream provenance](research-0.8-upstream-rust.md) for the original module boundaries.
No newly selected third-party runtime library was added.

复用已有 MIT 许可的 dsh-ops-core 与已锁定 serde 依赖，保留原许可；没有新选第三方运行库。
