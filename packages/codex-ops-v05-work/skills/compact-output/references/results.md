# Cached query operations

Chinese: [缓存查询](results.zh-CN.md).

These operations inspect saved observations and never repeat a producer. `outline`,
`find`, `items` and aggregation use the decoded MCP/inline payload; `raw` preserves
the exact original saved text or JSON. Paths are RFC6901 JSON pointers.

```javascript
await tools.mcp__codex_ops__ops_result({
  action: "batch", max_bytes: 12000,
  requests: [
    {ref: resultRef, view: "find", query: "timeout", limit: 5},
    {ref: resultRef, view: "count", path: "/records", query: "failed"},
    {ref: resultRef, view: "group", path: "/records", fields: ["status"]}
  ]
});
```

Batch accepts 1–8 requests and divides the total byte budget among them. All supplied
page options are validated before any retrieval. Each result retains its own errors,
scan state and continuation. Batch `complete` means every request was processed,
not that every source or page was complete. Release is a separate single-ref action.

Count uses a literal query over each record. Group accepts scalar records directly,
or exactly one top-level field of object records; missing fields are counted separately.
Aggregation scans at most 100,000 records and retains at most 1,000 distinct groups;
group keys are at most 1,024 encoded bytes. Narrow path/query after a truncated scan.
These are saved-observation counts, never an assertion that the original search was exhaustive.

Each page/batch is bounded by `max_bytes` 512–16000. Batch needs enough room for
at least 512 bytes per request plus its envelope. Record-view limit is 1–200;
raw ignores limit and uses a Unicode-character offset. Batch paths are at most
2,048 characters, queries 200, and fields 32 names of at most 256 characters each.

Explicit bounded pages and result batches bypass automatic recapture. Retrieval
cost counters measure returned pages separately from their eventual presentation;
they must not be added to presentation bytes as if they were disjoint costs.
