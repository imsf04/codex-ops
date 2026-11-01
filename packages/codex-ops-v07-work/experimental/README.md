# Automatic code-mode presentation prototype

This documents the original isolated stdio prototype. Version 0.2.0 builds on it
with the [Desktop gRPC runtime bridge](../runtime_bridge/README.md).
Chinese: [说明](README.zh-CN.md).

## Result

The unmodified local `codex-code-mode-host.exe` can retain full delegated tool
values while a separate process compacts only its outbound presentation frames.
The JavaScript fixture uses ordinary `text(r)`, `notify(r)` and `yield_control()`;
it contains no `ops_capture` call or helper replacement. After output, the script
still checks all 200 records, Unicode, false and null. Stored observations reconstruct
the exact emitted text. This proves the runtime separation, not Desktop deployment.

Native-runtime results (UTF-8 text bytes, not token estimates):

| Scenario | Native | With bridge |
|---|---:|---:|
| text | 100,148 | 3,953 |
| notify | 100,148 | 3,953 |
| yield + wait + notify | 300,424 | 11,839 |
| script failure | 100,138 | 100,138 |
| unavailable result store | 100,148 | 100,148 |

Ten baseline/bridge executions passed. Seven presentation unit tests cover media
ordering, control/delegate passthrough, errors, unknown frames, and metadata.
Media was tested as protocol data, not through a visual Desktop round trip.
Evidence: `../verification/code-host-report.json`, including native executable SHA-256
and individual frame traces in isolated temporary directories.

## Why hooks cannot install this behavior

On Codex 0.165.0-alpha.1.2, all-matching PreToolUse and PostToolUse observers received
no events for outer exec text, notify, yield, or wait. A nested MCP positive control
does trigger those observers. One-time JavaScript setup is not an installation
mechanism: exec uses a fresh V8 isolate for each cell.

The official configuration reference exposes code-mode enablement and tool routing,
but no plugin initializer or output-transform callback. The official developer
commands page documents an app-server `--code-mode-host` endpoint. On this installed
build, a `ws://` endpoint is rejected with `code-mode host URL must use http:// or
https:// with a host`; the bundled host advertises stdio and gRPC listeners. The
documented WebSocket example is therefore not a verified deployment recipe here.

The subsequent gRPC adapter and native CLI shim implement the Desktop connection.
A plugin manifest alone does not select that host. The stdio prototype below stays
available as an isolated test harness; production uses `runtime_bridge`.

## Implementation boundary

- `code_mode_bridge.py` launches an owned, unmodified native host and relays its
  length-prefixed JSON stdio protocol. Inbound frames are byte-identical, including
  `delegate/response` tool results, execution source and cancellation.
- `presentation.py` transforms only text content in `execute/initialResponse`,
  `wait/completed` live-cell outcomes, and `notification/send` delegates. It preserves
  invocation IDs, cell IDs, timing, control messages and non-text media.
- Failed scripts keep buffered diagnostic output. A notify already emitted before
  a later failure may already have a reference; the later error remains unchanged.
- Storage or unknown-schema failures preserve original frames. References contain
  emitted text, not the internal typed object; use `ops_result(view="raw")` to page
  it. Bytes already truncated by the native host cannot be restored.
- The protocol was observed from owned local processes. REA MCP/CLI was unavailable;
  these are subprocess/IPC observations, not decompiler or REA Evidence claims.

## Reproduce

From the dsh-ops checkout:

```console
python -m unittest discover -s packages/codex-ops/tests -p test_presentation.py -v
python packages/codex-ops/tests/run_code_host_tests.py
```

The bridge entrypoint is a binary stdio transport, not a chat-facing MCP tool:

```console
python packages/codex-ops/experimental/code_mode_bridge.py --upstream PATH_TO_CODEX_CODE_MODE_HOST_EXE
```

Do not redirect arbitrary human text into that transport. No extra dependency is
required; it uses Python's standard library and the existing result store.

Sources: [Hooks](https://learn.chatgpt.com/docs/hooks),
[configuration](https://learn.chatgpt.com/docs/config-file/config-reference),
[developer commands](https://learn.chatgpt.com/docs/developer-commands).
