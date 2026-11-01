# Reference ownership

Native MCP chat metadata, not tool arguments, binds new references to a chat.
Available sandbox and approval metadata contributes a permission fingerprint;
changing it makes the old reference unavailable to MCP retrieval. Deduplication
includes ownership so equal content in different chats does not share a reference.
Release observes the same checks as reading.

Automatic Code Mode text references are bound to the native runtime manager.
The Code Mode session UUID is not the Codex chat ID; no mapping is guessed.
Chats attached to that same runtime can retrieve those bearer references, while
another runtime cannot. A runtime restart can therefore invalidate access before
the storage TTL. Legacy 0.5 references retain their existing user-local bearer
behavior until expiration. New MCP requests without native chat metadata bind to
the verified runtime or, if unavailable, the local MCP server process; executable
reference plans require native chat identity. Internal library calls do not claim
host identity. The APIs do not guess chat ownership from runtime IDs.

Direct PostToolUse hook captures and internal library captures retain user-local
bearer behavior; they are not claimed to have the native MCP permission fingerprint.
The scoped automatic-output path above is the Code Mode bridge.

Native plan loading checks the thread ID supplied by the native execution
environment. Execution still runs under Codex's current sandbox and approval
policy; a reference, metadata field or plan never grants filesystem authority.
Task journals remain protected by the explicit workspace's native permissions.

This is application-level isolation, not a security boundary against a hostile
process running as the same OS user. Storage paths and local tool clients remain
accessible to that user. Read failures do not authorize rerunning mutations.

Run `python doctor.py --check-files` or `ops_stats(check_runtime=true)` to inspect
the package, configured override and runtime actually attached to the observing
process. Stage hashes are checked on request. Hook trust is inspected through
native `hooks/list`, never inferred from files or from the plugin's own assertion.
