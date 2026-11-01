# DSH real-use call chains / DSH 真实使用调用链

Date / 日期：2026-10-30. Scope: read-only inspection of four existing local sessions; no source operation was rerun, no production configuration changed, and no paid model trial was started. This is a purposive sample of code/research/document work, not a randomized comparison or eligible-opportunity adoption estimate.

## Observed sessions / 会话样本

| Session suffix | Work category | Outer tool calls | PTC completions | OPS-named calls |
| --- | --- | ---: | ---: | ---: |
| db1bcfbf | Rhino desktop development/release | 194, all run_code | 232 | 154 ops_bash inside PTC |
| 18964351 | RPU research | 312 native calls | 0 | 309: bash 230, inspect 34, replace 27, grep 14, glob 4 |
| 5e05f0b4 | RPU implementation | 212, all run_code | 386 | 185 inside PTC: bash 184, glob 1 |
| a73fe82d | Slide/tutorial document work | 73, all run_code | 151 | 48 ops_bash inside PTC |

OPS tool use is frequent in real work. The PTC samples mainly use ops_bash together with native read/edit/write, job_output and other tools. The native RPU sample exposes the OPS file surface directly. Its 309/312 share is a count of selected tool names under that preset, not an independently established preference for OPS over equally visible alternatives.

真实任务中 OPS 使用频繁，但需要区分入口：PTC 样本主要调用 ops_bash，文件读写仍大量使用宿主 read/edit/write；原生预设样本则直接使用 OPS 文件工具。309/312 不能解释成模型面对相同可见选项时的自发选择率。

The current installed desktop plugin was separately checked by the main audit as version 0.3.0, with shell/file enabled and the OPS-specific PTC component disabled. Historical sessions do not establish a version for every call. These logs therefore do not measure current upstream 0.5 or prove that its advanced SDK was naturally adopted. Host PTC run_code works independently of that plugin component.

当前安装核对为 0.3.0，不能把这些历史记录写成最新上游 0.5 的真实效果。宿主 run_code 可以正常使用；OPS 专用 PTC 组件当前被禁用，因此没有使用该 SDK 不能简单归因于模型不愿采用。

## Useful complete chains / 能够直接看到的收益

**Rhino, seq 614 → 616/618/620 → 621.** One run_code reads a small file range, edits the version and invokes ops_bash for the associated package/git operations. Three internal tool calls finish in one model action. Internal text content totals 753 characters; the original outer emitted text is 480 characters. This verifies composability and selective printing. It does not establish three avoided model turns against a baseline.

**Rhino, seq 606 → 609 → 610.** A native job_output result has 49,931 text characters; PTC prints status and the last 800 characters, emitting 810. The emitted tail contains the test summary and completion status. This is a concrete reduction in model-visible text through code projection. job_output is a native tool; this example is not attributable to the dsh-ops compressor and is not a token/billing savings measurement.

Across this Rhino session, 158 run_code calls dispatch one tool, 34 dispatch two and 2 dispatch three. All 194 roots have completed dispatch records. The important convenience is that data can remain inside code while only the needed result is printed.

Rhino 的同一调用中能完成“读一小段 → 修改 → 执行检查/版本操作”，无需逐个工具结果都成为下一轮推理输入。长任务的状态和摘要也能由代码直接挑选后输出。这种体验来自宿主 PTC、类型化结果和有选择的输出共同作用，不能全部记为插件压缩收益。

## Friction and failures / 真实摩擦

1. **Timeout argument mismatch and another poll.** Rhino seq 251 requests inner job_output timeout_ms=540000 and supplies outer run_code timeout_ms=560000. Seq 254 nevertheless reports a 120000 ms outer deadline; seq 258 polls the job again. The spelling differs from timeoutMs used in other run_code calls in the same log. The record demonstrates a timeout-contract mismatch; identifying every runtime parser rule is outside this audit.
2. **Short output can still be irrelevant.** Rhino seq 939 invokes ops_bash for a recursive search, with head -20 and a JavaScript slice to 6000 characters. Dispatch seq 941 still contains 49,932 characters of generated coverage/minified JSON; result seq 942 displays 6000. Limiting lines and bytes alone did not prevent generated artifacts from occupying the evidence budget.
3. **Tool-envelope success is not command success.** In the slide task, seq 376 combines read, write and rebuild. OPS dispatch seq 382 reports a program error and [exit code: 1], while isError remains false. Outer seq 383 prints the error traceback but drops the explicit exit-code field. Subsequent fixes at seq 387 and 398 eventually produce a saved artifact at seq 404/405. This is a business-program failure and repair, not evidence of an OPS runtime crash.
4. **Host compaction rewrites displayed history.** The Rhino sample has 199 tool/result records for 194 unique call IDs; the earlier RPU sample has 229 records for 212 IDs. Their extra result records match 5 and 17 prune events. Counting all recorded result bodies as simultaneously displayed output double-counts replacement states. Outer call IDs and PTC subCallIds are unique in all four samples.

超时参数、生成文件噪声、退出码遗漏都在真实日志中出现。可以借鉴 PTC 的组合执行，同时让 Codex Ops 自动保留关键状态和错误、按材料类型选取证据，并减少需要模型记住的参数差异。历史压缩属于宿主能力；不能把其全部收益计入插件。

## Implications for Codex Ops / 对 Codex Ops 的启示

- Make common execution/inspection paths immediately usable in the host's normal tool surface. High usage here is supported by visible/default tools and shell guidance, not evidence that a large optional catalog is sufficient.
- Support useful bounded composition and printing once; preserve full values inside code. Do not force a separate helper-loading round trip for every routine operation.
- Show terminal state, exit code, failure and partial-success information even when users/model code print only stdout or a small excerpt.
- Exclude generated artifacts and select the requested evidence before spending the display budget. A smaller minified blob is still a poor answer.
- Separate plugin contribution, native PTC contribution and host historical pruning in measurement.
- The samples do not provide a controlled no-plugin baseline, task success oracle, complete cost comparison or evidence that Rust caused the observed convenience.

高频入口、组合操作和结果直达值得借鉴；费用降低、完整任务成功率和 Rust 的因果收益仍需要对照。插件版本、预设、模型与任务也需要分组。

## Local sources / 本地来源

All sequence identifiers refer to event seq fields in the compressed JSONL, not line numbers.

- [Rhino session](C:/Users/imsfp/.dsh/sessions/--D-huixi-rhinostudio--/session-db1bcfbf-2528-43e9-b396-3c7d3d123f5e/session.v4.jsonl.zstd): seq 251–258, 606–621, 939–942.
- [Native RPU session](C:/Users/imsfp/.dsh/sessions/--D-Desktop-26fallddm-MSDM6980-1022_2nd_group_meeting--/session-18964351-4441-484b-93a3-939035fefd6e/session.v4.jsonl.zstd): complete session tool-name census.
- [PTC RPU session](C:/Users/imsfp/.dsh/sessions/--D-Desktop-26fallddm-MSDM6980-1022_2nd_group_meeting--/session-5e05f0b4-46c7-4ada-81e6-3dc4be1e5b31/session.v4.jsonl.zstd): complete session tool-name/identity census.
- [Document session](C:/Users/imsfp/.dsh/sessions/--D-Documents-deepseek-harness-default-workspace--/session-a73fe82d-78ad-4cde-9ebd-31198b209387/session.v4.jsonl.zstd): seq 376–405.
- Analysis helpers: [inspection](../verification/dsh_chain_inspect.py), [projection/semantic check](../verification/dsh_chain_metrics.py), [ID check](../verification/dsh_chain_identity.py). They read sources without modifying them. JSON/JSONL and Zstandard use the Python standard-library implementations.

