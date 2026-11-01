# Codex Ops 0.8: upstream comparison and Rust decision / 上游比较与 Rust 决策

Research date: 2026-10-30. Scope: primary-source inspection and existing local measurements; no production changes, upstream merge, dependency installation, or paid model trials.

## Recommendation / 建议

Keep the existing Rust engine and narrow the Python-to-worker boundary before considering a full rewrite. The first candidate should collapse a bounded investigation into one worker request, preserving per-step observations and errors. Whether the orchestration eventually belongs in Rust is a measurement decision; translating Python while retaining four worker starts does not remove those starts.

建议 0.8 首先复用已有 Rust 内核，将有边界的调查流程合并为一次 worker 请求，同时保留每一步证据、权限、错误和取消语义。先验收局部优化，再决定哪些 Python 模块值得迁移；不把“全量 Rust 重写”等同于稳定性或端到端收益。

## Versions and evidence / 版本与证据

- GitHub main was verified as [02b1c0c147025ae30df977227cdbfd68c6f77a2e](https://github.com/T-Auto/dsh-ops/commit/02b1c0c147025ae30df977227cdbfd68c6f77a2e), committed 2026-10-29 13:08:03 UTC. Its package version is still [0.5.0](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/package.json). Codex Ops 0.7 is a separate adapter version, not a later release of the upstream package.
- The local upstream checkout is 61ef5539b080e94e38206a05cceb82bfadee3406. The [pinned comparison](https://github.com/T-Auto/dsh-ops/compare/61ef5539b080e94e38206a05cceb82bfadee3406...02b1c0c147025ae30df977227cdbfd68c6f77a2e) reports 19 commits ahead, zero behind, and 74 changed files. None is under native/. This comparison measures upstream checkout drift, not semantic equivalence of the separately maintained, locally untracked packages/codex-ops directory.
- Codex Ops 0.7 was accepted for local activation with releaseGatePassed=false. Its 28 common-success pairs reduced native actions 19.29% against a 25% target and input 16.04% against a 20% target. [Release report](release-0.7.0.md) records the retained failures and unknowns. A language migration cannot retrospectively satisfy those gates.

上游当前包版本仍为 0.5.0；Codex Ops 0.7 是独立适配层的版本。最近 19 个提交没有修改 native Rust 目录，主要变化属于宿主集成、工具发布、发现与生命周期。现有 0.7 的成本目标未通过，不能通过改写实现语言改判结果。

## Concrete comparison / 具体差异

| Area | Current upstream | Codex Ops 0.7 and implication |
| --- | --- | --- |
| Execution core | Rust protocol/files/search/documents/results/batch crates, plus TypeScript host projection. [Cargo manifest](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/native/Cargo.toml), [dispatch](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/native/src/lib.rs) | [files.py](../files.py) already invokes dsh-ops-worker.exe for read/search/document operations. This is already a hybrid implementation. |
| Host publication | New explicit preset-scoped opt-in; files, shell, discovery, guidance and replacements are independent. Installation/import alone publishes nothing. [Integration API](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/docs/integration-api.md) | Codex has its own MCP/Code Mode bridge and [Rust launcher shim](../runtime_bridge/shim.rs). DSH Cordis integration is not a drop-in Codex API. Reuse lifecycle and publication principles, then implement/test against the actual Codex host. |
| External providers | Native provider registration, explicit allow/deny/startup sets, unload invalidation, execution-time authority checks. No third-party PTC SDK registration contract. [Provider contract](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/docs/external-provider.md) | A capability to compare, not proof that Codex can dynamically publish the same tool surface. Full Rust conversion supplies none of these host APIs automatically. |
| Presentation | Separate Native rendering and typed PTC outcome projections; latest fix handles deferred assembled tool arrays. [Host integration](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/docs/host-integration.md), [latest fix](https://github.com/T-Auto/dsh-ops/commit/02b1c0c147025ae30df977227cdbfd68c6f77a2e) | Audit Codex evidence packets and machine-readable envelopes separately. Payload shape and reread incentives can dominate task cost independently of CPU language. |
| Codex workflows | The recent upstream diff does not introduce Codex-specific workflows. | 0.7 already adds bounded question-to-source investigation, authorized cross-reference FTS5 search, working-set resume, native verification and usage accounting. These are product contracts to preserve, not erase during an engine migration. [Workflows](workflows-0.7.0.md), [release](release-0.7.0.md) |
| Host restrictions | Upstream documents inherited-vs-owned tool masking, unsupported nested preset isolation, and provider-history serialization boundaries. [Host integration](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/docs/host-integration.md) | These are DSH-specific findings. For Codex, use its own native evidence: 0.7 still records unresolved working-directory/PowerShell/sandbox and terminal-evidence failures. Rust does not grant different host authority or repair provider message serialization. |

## Full-capability classification / 全能力分类补充

The comparison above includes the recent upstream delta; this table checks the broader product surface. It does not assign a parity percentage or equate similarly named tools with identical contracts. Upstream sources: [component catalogue](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/docs/component-reference.md), [CLI and panel](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/docs/usage.md), [diagnostics](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/docs/diagnostics.md).

| Capability | Upstream baseline | Codex 0.7 classification |
| --- | --- | --- |
| File search/read, metadata, differences and documents | Rust fixed operations; separate Native/PTC projections | **Shared engine and available capability**, with Codex-specific arguments, scope, presentation and workflow wrappers. This is not blanket full-contract parity. [files.py](../files.py) |
| Precise writes and edits | write_file/edit_file with revision/CAS and single-file atomic edits; mechanical replace; audited copy/move/remove batch | **Available with deliberate native execution delegation.** ops_plan already supports write/edit/replace/copy/move/remove, saves a CAS plan and returns CLI arguments for native exec_command. ops_task adds staged file/tree recovery and rollback. MCP does not apply changes. Stages are checkpoints, not atomic multi-file transactions. [server.py](../server.py), [tasks](tasks.md) |
| Built-in PTC execution and SDK loading | Typed built-in SDK runs through DSH's actual PTC presentation and host governance; advanced APIs can be loaded | **Different host contract, not full parity.** Codex supplies an optional JavaScript workflow helper and uses existing Code Mode/native tools. Its documentation explicitly does not claim native dynamic SDK registration. This is not evidence that Codex lacks arbitrary code execution. [README](../README.md), [workflow contracts](workflows-0.7.0.md) |
| Windows shell and long-running processes | ops_bash with a matched private IPC runtime and host confinement; host PowerShell remains available | **Deliberately delegated.** Codex command execution, permissions and polling stay with native exec_command/write_stdin; workflow verification consumes their results. No general MCP shell executor is needed for parity of user outcomes. [server.py](../server.py) |
| Native tool replacement and progressive publication | DSH modes can hide official counterparts only while replacements are visible; compatibility mode restores official visibility | **DSH-specific host integration unavailable as a drop-in Codex API.** Codex's output bridge and ops_catalog documentation are different mechanisms. Porting Rust does not create registry replacement authority. [README](../README.md), [integration API](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/docs/integration-api.md) |
| Diagnostics, panel and dashboard | Scoped ops_status, captured conversation panel and optional DSH TUI sidebar | **Partly analogous functionality already present.** ops_stats, doctor.py and dashboard.py provide installation/runtime diagnostics and offline HTML or explicitly started loopback views. DSH's scoped publication diagnostics and embedded TUI are distinct host features, not proof that Codex has no diagnostics/UI. [doctor](../doctor.py), [dashboard](../dashboard.py), [README](../README.md) |
| Installation and operational CLI | DSH-profile install/uninstall/status, runtime provisioning, build and panel commands | **Host-specific equivalents and different scope.** Codex uses its own plugin installer, rollback/bridge tooling, doctor/dashboard and mutation/task CLIs. Importing DSH provisioning commands is not a Codex requirement. [deployment](../runtime_bridge/README.md), [mutation CLI](../mutations/cli.py) |

中文：不能把“未暴露为独立 MCP 工具”统计成“能力缺失”。0.7 已有精确写入/编辑计划、CAS、原生命令执行、恢复回滚、诊断和 HTML 看板；其中命令与变更执行刻意交给 Codex 原生权限链。真正未直接对齐的是 DSH 的动态发布/替换、内置 PTC 注册协议、宿主侧栏和对应运维体系。它们需要宿主接口与产品选择，不能靠 Rust 重写获得。多文件阶段计划也不能表述为全局原子事务。

## Reuse boundaries / 复用边界

1. **Reuse the native library, not a replacement search engine.** dsh-ops-core exposes dispatch(Request); ops-files, ops-search and ops-documents already own the expensive filesystem/document functionality. The workspace uses Rust 1.88, edition 2024, path dependencies; the individual core crates are marked publish=false. Pin the source revision and build its workspace rather than assuming identically named published crates exist. [Manifest](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/native/Cargo.toml), [search manifest](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/native/crates/ops-search/Cargo.toml).

2. **Existing batch is not the required compound read operation.** ops-batch is an audited mutation workflow; Operation::Kind is Copy, Move or Remove. A read/search investigation needs a new bounded composition contract or adapter, with one authority root, explicit budgets, per-step completeness and error results. Do not route it through the mutation journal merely because the crate is named batch. [Operation contract](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/native/crates/ops-protocol/src/lib.rs), [batch implementation](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/native/crates/ops-batch/src/lib.rs).

3. **Do not turn the CLI into a daemon by adding a loop.** The existing worker reads stdin to EOF, executes one request, and starts a process-wide deadline thread that exits with code 124. A persistent worker requires request framing, per-request cancellation, authority separation, cleanup and crash recovery. In-process library reuse must replace the CLI-owned timeout/lifecycle behavior explicitly. [Worker main](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/native/src/main.rs). Prefer one compound request per process as the smaller initial change.

4. **Keep the existing launcher separate from the execution engine.** The local Rust shim adds --code-mode-host to eligible app-server service starts, manages Windows jobs and forwards to the real CLI. Its existence is not evidence that Python workflow/result handling has already migrated. [Shim](../runtime_bridge/shim.rs).

5. **Result-store contracts require adaptation.** Upstream ops-results owns native result/audit persistence, while local [store.py](../store.py) provides scoped SQLite observations, digests, reference paging and authorization. A direct storage swap must preserve existing references, ownership, expiry, exact retrieval, restart and rollback semantics. The fact that both implementations store results is not API or storage-format compatibility. [Upstream store](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/native/crates/ops-results/src/store.rs).

6. **FTS is already a native database operation.** Local [evidence_index_query.py](../evidence_index_query.py) creates an in-memory SQLite FTS5 table with unicode61 and executes MATCH. Translating the Python wrapper does not change FTS tokenization/ranking or reuse the index automatically. If profiling identifies rebuilding as a cost, test an authorized reusable index before changing languages. Preserve visibility/expiry checks and ranking behavior. [SQLite FTS5](https://www.sqlite.org/fts5.html).

中文：优先复用现有库入口与文件、搜索、文档模块。现有 batch 仅处理 copy/move/remove，不能当作调查批处理。CLI 的 EOF 输入和进程退出式超时不支持直接常驻化；Rust shim 只是启动和生命周期管理。结果存储与 FTS 迁移须保留引用、权限、分页、排序及回滚契约。

## Performance evidence and decision order / 性能证据与推进顺序

The [local serial profile](../verification/v08-local-profile.json) records seven repetitions per case with an isolated validation store. It excludes MCP transport, model latency and cold-start measurement.

| Case | Median |
| --- | ---: |
| Native read, 44 lines | 26.02 ms |
| Investigation, one anchor and one file | 112.08 ms |
| Present approximately 61 KB of log output | 6.23 ms |

The investigation trace shows four native-worker subprocess calls (grep/read/grep/read), each roughly 27 ms. This identifies repeated worker boundaries as a promising target in this fixture; the timings include operation/serialization work and do not isolate pure process-start overhead. It does not establish an end-to-end speed multiplier or task token reduction.

Recommended sequence:

1. Record the current bytes/shape and required observations alongside time, call counts, cold/warm startup and p50/p95 under representative sizes.
2. Prototype one bounded compound investigation using the existing Rust crates; compare equal outputs and authority/cancellation behavior against 0.7. Keep the existing Python MCP/host layer initially.
3. Measure packet size and reread behavior independently of worker latency. Change repeated metadata/selection rules only with a retrieval-completeness contract and fixtures.
4. Consider persistent processes or PyO3 only if the remaining measured boundary cost justifies their deployment/lifecycle complexity. PyO3 offers Python/Rust integration and detach for Rust work, but its documentation is not a performance measurement for this application. [PyO3 parallelism](https://pyo3.rs/main/parallelism).
5. Migrate further Python modules only when their measured cost or deployment failure mode warrants it, preserving the accepted 0.7 baseline and rollback.

中文：局部实测表明单文件调查触发四次 worker 调用，应先减少边界穿越。112 ms 是该微基准的中位数，不包含模型和 MCP 的完整链路；每次约 27 ms 也不能全部归为纯进程启动时间。合并调用、缩减重复元数据、后续语言迁移应分别验收。

## Stability, quality gates and provenance / 稳定性、质量门禁与来源

Rust's Result and panic mechanisms make failure handling explicit but do not prove protocol compatibility, authorization correctness, crash recovery or task success. The upstream core forbids unsafe code in its own modules; the local Windows launcher necessarily has a different boundary. Keep failure results, timeout/cancel, partial observations and effectState assertions independent of implementation language. [Rust error handling](https://doc.rust-lang.org/book/ch09-00-error-handling.html), [upstream dispatch](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/native/src/lib.rs).

The 0.7 report's all-797-functions CRAP <=6 and 99.25% combined statement/branch coverage apply to 83 Python production/installation modules, explicitly excluding Rust and embedded JavaScript. Retain that Python gate for remaining Python. Before accepting Rust production additions, define function-level complexity and coverage calculation, included code, thresholds and unsupported constructs; rustc's LLVM coverage instrumentation alone is not a CRAP score and does not establish equivalence with the Python measurement. If the required Rust CRAP gate is not implemented, report it as unverified rather than passing the project by omission. [0.7 report](release-0.7.0.md), [rustc coverage](https://doc.rust-lang.org/rustc/instrument-coverage.html).

Upstream [LICENSE](https://github.com/T-Auto/dsh-ops/blob/02b1c0c147025ae30df977227cdbfd68c6f77a2e/LICENSE) and the local [LICENSE](../LICENSE) are MIT, copyright 2026 T-Auto and the dsh-ops contributors. Retain the copyright and permission notice when redistributing substantial source or binaries and audit bundled dependency notices separately. Reusing this existing first-party project workspace is lower provenance friction than importing an unrelated engine; it is not exemption from dependency review. The 0.7 [reuse note](open-source-0.7.0.md) says no new third-party source was copied for that implementation; it should not be misread as a claim that the whole adapter has no upstream-derived native dependency.

中文：Rust 的类型和错误机制不能替代宿主协议、权限和恢复测试。原有 CRAP 指标只覆盖 Python；新增 Rust 若没有明确复杂度与覆盖率计量，应记为未验证。复用上游 MIT 代码要保留版权与许可，继续记录依赖来源，不能把“0.7 未新增第三方源码”解释成“整个插件与上游无关”。

