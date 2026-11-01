# Evidence and frame budgets

The 0.6 presentation layer keeps the raw source value and its exact emitted text.
Completed shell results can show bounded TypeScript/build diagnostics, Python or
pytest failures, Git diff evidence and Git short-status paths. Diagnostic previews
include line numbers, completion summaries, source locations and explicit counts
of omitted diagnostics and lines. They are evidence samples, not proof that the
unshown output contains no additional failures. Source-code listings are not
promoted into logs merely because they contain an error string.

Common JSON lists with names, titles or statuses show a bounded record
sample, retaining identifiers and paths where present. Failed records are prioritized even when they occur beyond the first
page. Counts describe the saved observation, not the upstream service's total.
The exact raw text remains available from the receipt's `ops://` reference.

When multiple text blocks in one outbound Code Mode frame exceed 12 KiB together,
they share a proportional presentation target. This can compact individually
small blocks that would otherwise accumulate without triggering a threshold.
The target is soft: explicit retrieval pages, media and native error-state bytes
keep their contracts; unhelpful compression or unavailable storage preserves the
original output. Every replacement must save bytes.
The frame budget only tightens a normal receipt that exceeds its allocation; it
never replaces an already smaller receipt with a larger preview.
Native tool return values inside JavaScript are unchanged. Repeated text can reuse a reference only within
the same execution result frame, never because it appeared in an earlier turn.

The actual-command comparison is in
`verification/v06-evidence-benchmark.json`. A useful preview can be larger than a
generic one: the Git diff case intentionally retains more evidence. Byte changes
alone do not demonstrate fewer model tokens, fewer follow-up reads or faster tasks.

Chinese: [呈现与预算](presentation.zh-CN.md).
