# On-demand operation contracts

Call `ops_catalog()` for a thin operation list. Select one with
`ops_catalog(operation="grep")` to receive its exact adapter `argsSchema`, example,
execution route and operational boundaries. Examples use an explicit placeholder
for an existing absolute root; replace it before calling the tool.

The nine read operations plus read batch and search route to `ops_files`. Six
mutation operations route to `ops_plan`; their schemas describe planner arguments,
not raw Rust worker arguments. The planner calculates expected revisions and
returns a native execution route. Discovery never executes changes or grants
authority. In particular, planner replace uses `oldText`, `newText` and
`expectedCount`, whereas grep uses a regex `pattern`.

Read batch permits 1–4 of the nine independent native read operations; it does not
nest another batch, search workflow, or mutation. Search performs its own bounded
two-stage workflow; see [query](query.md).

Schema bounds catch common shape mistakes. Native semantic checks remain
authoritative: a valid schema alone cannot prove a supported PDF encoding,
permission, positive glob, current revision or unique edit match. Interpret
`status`/`error` before using a result. Obtain the selected contract to correct an
argument error, narrow a partial search, and inspect mutation state after uncertainty.

This is demand-loaded documentation returned through an MCP tool. It does not claim
to register new Codex tools dynamically or replace the host's generated SDK.

中文：[按需参数契约](catalog.zh-CN.md)
