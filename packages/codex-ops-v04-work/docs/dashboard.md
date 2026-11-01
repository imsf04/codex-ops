# Local statistics snapshot

Export one self-contained HTML file from the production uv environment:

```powershell
& "$env:USERPROFILE/.local/share/codex-runtimes/codex-ops-uv/Scripts/python.exe" `
  "C:/Users/imsfp/code/dsh-ops/packages/codex-ops/dashboard.py" `
  --output "C:/Users/imsfp/Desktop/codex-ops-stats.html" --origin production
```

Open that file in a browser. Change `--origin` to `validation` for test counters.
`--store` optionally selects another existing local data directory. Export requires
an absolute `.html` output path; it replaces that selected file when run again.
The page works offline, starts no server, and loads no external assets.

The two tables can be filtered and sorted. Presentation groups include tool,
hashed session identifier, processing reason and emitted channel. Retrieval groups
identify the producing tool/session when the reference has unambiguous linkage.
Missing evidence and legacy records remain unattributed. A session identifier
represents the proven runtime scope, not necessarily a whole Codex chat.

Presentation counters measure emitted UTF-8 bytes before and after compression.
Retrieval counters separately measure successful `ops_result` response bytes;
the latter may subsequently be emitted, so the page does not add or subtract
them to claim net savings. A repeated bounded-page request is not necessarily
avoidable work. These values do not measure tokens or task success.

Generation time and newest sample age describe this static snapshot. No exact
daily time range can be reconstructed from retained aggregate counters. Re-export
to refresh. The exporter reads cache metadata in a read-only SQLite transaction:
it does not inspect saved payloads, create the cache, or prune expired references.
The HTML contains aggregate labels and opaque session hashes, never saved outputs.

中文：[本地统计快照](dashboard.zh-CN.md).
