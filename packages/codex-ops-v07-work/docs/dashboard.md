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

Generation time and newest sample age describe the snapshot. `--window all` keeps
the legacy instance-lifetime view. `--window hour`, `day` or `week` selects completed
five-minute buckets ending at the latest five-minute boundary. The current partial
bucket is excluded, so a fresh install may show no recent-window events for up to
five minutes. Collection start, exact interval and bounded-history loss are explicit;
old unbucketed records are never reconstructed as recent activity. Bucket data is
retained for seven days, at most 32,768 rows per origin. A bucket keeps 128 detailed
dimensions plus an unattributed overflow group; overflow counts remain visible.

Add `--tasks-root C:/absolute/workspace` to inspect saved mutation-journal phases for
that one workspace. The scan reads at most 512 directory entries and 64 summaries,
with a 16 MiB total JSON budget. It does not inspect backups or revalidate current
file postconditions. Inaccessible, malformed and bounded-out entries are explicitly
incomplete. Command arguments, content, error bodies and file paths are not exported.

For an explicitly started refreshable view, replace `--output ...` with `--serve`
and optionally `--port 0`. The CLI prints a random `http://127.0.0.1:PORT/` address;
open it and click Refresh to query a new snapshot. Stop with Ctrl+C. This is a
foreground, loopback-only GET service, not an automatic background process. Store,
origin, period and task root remain fixed at startup; request query parameters cannot
select another directory. Unknown Host/Origin and mutation requests are rejected.
Only the page and aggregate `/snapshot` are served; no arbitrary files or operations.

Static files remain offline snapshots; re-export to update them. The exporter reads
cache metadata in a read-only SQLite transaction:
it does not inspect saved payloads, create the cache, or prune expired references.
The HTML contains aggregate labels and opaque session hashes, never saved outputs.

中文：[本地统计快照](dashboard.zh-CN.md).

The dashboard also distinguishes package, configured and observing-process runtime versions. A staged-task journal contributes task kind, stage count and completed steps, under the same shared scan/byte budget as legacy journals.
