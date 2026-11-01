---
name: compact-output
description: Investigate code questions with source context, diagnose logs, search acquired evidence, and resume task evidence. Use for multi-step investigation, related documents and ops:// results.
---

Keep full tool values inside functions.exec and emit ordinary text()/notify().
The active runtime compresses large displays; original program values stay intact.

For a code question, call ops_workflow directly with an absolute root:
operation="investigate",args={question:"Where is retry_delay capped?",anchors:["retry_delay"]}.
Anchors are optional literal symbols/phrases. Use identifiers for opaque business
terms. Read source evidence and coverage; needs_anchor asks for a precise clue.
A match supplies evidence, not proof of a semantic answer.

Other direct routes:
- Saved sources: operation="evidence",args={refs:[...],query:"relevant terms"}.
  Searches 1..8 authorized observations lexically. Use returned content directly.
- Log file: operation="diagnose",args={logPath:"build.log"}. Original line numbers
  are retained. Already-read text can use log or logRef instead, exactly one.
- Related inputs: operation="documents",args={requests:[{operation:"read",
  args:{files:[{path:"notes.md",offset:1,limit:100}]}}]}. For tables use read_table
  with {path:"prices.csv",limit:1000}. Small results are inline; check page coverage.
- Recovery: operation="working_set",args={action:"save",sources:[{ref}],pending:["check tests"]};
  later {action:"resume",workingSetRef}. Changed or expired sources are explicit.
- Native command chunks: operation="verify",args={results:[nativeResult,...]}.
  This analyzes existing results. Optional sdk provides verifyRun for native
  execution and bounded polling; preserve its raw results and terminal status.

Single known reads, writes and polling stay native. Set exec_command workdir.
Exact range comparisons and staged file changes: [advanced contracts](references/advanced.md).

Use inline evidence directly. ops_result supports batch queries and selected
fields; view="raw" with nextOffset reconstructs exact text. Retrieve missing
evidence rather than rerunning its producer. Preserve error and media envelopes.
ops_stats separates actual task tokens from presentation bytes; neither implies
counterfactual savings without a paired comparison.
