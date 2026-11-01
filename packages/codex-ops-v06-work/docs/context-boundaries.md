# Context evidence and repetition

Codex Ops reuses an exact text reference inside one outgoing Execute or Wait
response. The first compacted preview and every repeat receipt travel in the same
response. Repeats identify the first text block and retain its raw reference and
metadata. A wrapper lives for that response only, with at most 16 entries and
2 MiB of source text. It does not reuse notification previews or earlier responses.
Source values, input protocol frames, media and native error states are unchanged.

This is not context-aware file-read deduplication across model steps. The installed
Codex 0.165.0-alpha.1.2 exposes rollout history through `thread/read`; its generated
schema explicitly calls `includeTurns` historical hydration. `thread/compacted`
reports thread and turn IDs; `ContextCompaction` items are its replacement. Neither
provides the exact current model-request message membership. `thread/sample`
performs a model sample and returns text/usage, not an authoritative context body.
The native Code Mode relay observes tool execution, not model prompt assembly.
Consequently, unchanged files, a cache hit, a transcript or a window ID do not
authorize omitting file contents across requests. That optimization remains absent.

## Attribution identities

The same installed host was tested with two executions in one chat, two chats in
one app-server, a yielded execution/Wait, and a native nested MCP call.

- Execute field 1 is a native Code Mode session UUID. It stays stable across
  executions in the same tested chat and changes across the two tested chats.
  Wait field 1 matches it. This is reported as `code-mode:<uuid>`, not a chat ID.
- Execute field 2 changes for each invocation. Wait field 2 is a cell ID.
  Neither is used as a stable session identity. Notification requests do not
  carry a verified session identity, so their attribution remains tool-only.
- MCP request metadata contains `threadId`, `windowId`, `itemId` and
  `x-codex-turn-metadata.thread_id`. The thread ID was matched to the owned
  app-server thread-start event. Conflicting identities are rejected. Valid
  metadata is reported as `chat:<threadId>`; no command or payload is retained.
- MCP context metadata is a dictionary supplied by the native request. It is
  read through injected `mcp.server.mcpserver.Context`, never through tool arguments.
  Its sandbox fields are not treated as permission to run unrestricted writes.

`bridge_context.py` only extracts bounded, version-tested attribution facts.
Missing, malformed and unknown fields leave session attribution unavailable.
These identities support accounting; they do not prove current prompt membership
or establish reference access control by themselves.

## Evidence

The local protocol schema was generated with
`codex app-server generate-json-schema --experimental --out <directory>`.
The native host's gRPC reflection endpoint returned `UNIMPLEMENTED`; wire-field
claims above come from the owned native execution probes, not descriptor guesses.
`verification/context-evidence/` contains the native frame receipt, MCP metadata,
identity observations and coverage results. The tests use a local deterministic
model server; they do not measure real model quality or token savings.

Chinese: [上下文证据与重复输出](context-boundaries.zh-CN.md).
