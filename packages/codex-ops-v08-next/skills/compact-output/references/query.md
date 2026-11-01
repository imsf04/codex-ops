# Search and context in one request

Use `ops_files(root, operation="search", args)` to locate matches and read nearby
source lines in one bounded request. `root` is an existing absolute directory.
The same native path, symlink/reparse and credential checks apply to both phases.

```json
{"path":"src","pattern":"def start","glob":["**/*.py"],"maxMatches":20,"maxFiles":4,"before":2,"after":5}
```

`pattern` is a nonempty Rust regex, at most 4096 characters. Optional `path` defaults
to `"."`; `glob` is an array of at most 32 nonempty strings. `caseInsensitive` is a
boolean, default false. `offset` is a zero-based search row offset, 0–1000000.
`maxMatches` is 1–64 (default 20), `maxFiles` 1–8 (default 4), and `before`/`after`
0–20 lines (default 3 each). Unknown fields and wrong types are errors.

The first phase asks the unchanged Rust worker for content matches, stopping early
at its row limit. The second phase merges overlapping/adjacent line ranges per file
and reads at most 32 ranges in one native batch. The shared deadline is 45 seconds,
each phase at most 22 seconds. There is no automatic retry.

Read `search.scanComplete`, `search.nextOffset` and native coverage facts before
concluding that a symbol is absent. `omittedMatches` and `omittedRanges` report
selection limits; increase bounds or narrow the path when necessary. `context`
contains native ranges, their revisions, continuation and per-file errors.

Search and read are **not an atomic filesystem snapshot**. `matchChecks` compares
each selected original matching line with its reread text: unchanged, changed, or
unavailable. This detects changed matching lines; it cannot prove unrelated parts
of the file stayed unchanged. Preserve both the original match and the newer range
when investigating a change. Truncated or pending context stays partial.

For an exact operation schema and valid example, call `ops_catalog(operation="search")`.
Describing an operation does not execute it or grant permissions.

中文：[搜索与上下文](query.zh-CN.md)
