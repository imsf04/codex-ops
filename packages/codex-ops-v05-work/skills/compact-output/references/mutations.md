# Planned file changes

Use `ops_plan(root, operations)` to prepare a bounded file-change plan. Planning
reads the files, checks the whole batch and stores exact expected revisions;
it does not change workspace files or grant execution permission. Save the returned
`ops://` plan reference and run the supplied execution command through Codex's
native `exec_command`. The native shell owns sandbox and approval decisions.
MCP never starts the mutation executor, and there is no model-supplied permission
mode or unsandboxed fallback.

Each operation is `{operation, args}`. Use 1–32 independent operations with
disjoint source and target paths under one existing absolute root. Paths can be
relative to that root; parent directories must already exist. Files are limited
to 1 MiB, plans to 8 MiB. Links, junctions, hard-linked files, directories,
credential names and journal paths are refused.

| operation | args |
| --- | --- |
| `write` | `{path, content}`; create or replace UTF-8 text |
| `edit` | `{path, edits:[{oldText,newText}]}`; 1–100 unique, nonoverlapping matches in the original text |
| `replace` | `{path, oldText, newText, expectedCount}`; replace exactly the stated number of nonoverlapping literal matches |
| `copy` | `{path,to}`; destination must be absent |
| `move` | `{path,to}`; destination must be absent |
| `remove` | `{path}`; a single explicit file |

Existing text-edit targets must be valid UTF-8. Copy, move and remove support
binary files. Exact CRLF, BOM and Unicode content is preserved unless explicitly
changed. Copy/move never overwrite a destination. All targets are checked before
any operation; the native Rust worker checks the expected revision again when
publishing each file. The batch is not a cross-file atomic transaction.

```powershell
& '<production-python>' '<plugin-source>/mutations/__main__.py' apply --plan-ref 'ops://...'
& '<production-python>' '<plugin-source>/mutations/__main__.py' status --root '<root>' --id '<journalId>'
& '<production-python>' '<plugin-source>/mutations/__main__.py' resume --root '<root>' --id '<journalId>'
& '<production-python>' '<plugin-source>/mutations/__main__.py' rollback --root '<root>' --id '<journalId>'
```

The source path and interpreter come from the installed plugin. Execute the actual
command via the native shell, preserving its exit/error/result. Do not interpret
a plan digest or possession of its reference as authorization.

Before execution, the CLI writes recovery snapshots and a journal under
`<root>/.codex-ops-mutations/<journalId>/`. The native worker performs the actual
publication. A failed/terminated call must be inspected with `status`; never
blindly repeat `apply`. Explicit `resume` compares current content with every
recorded before/after condition, skips completed changes and refuses unexpected
changes. `rollback` checks the entire batch before restoring exact original bytes;
an interrupted rollback can be continued by calling `rollback` again. Once rollback
starts, resuming forward execution requires a new plan.

Recovery restores file bytes and existence. It does not promise to restore the
original ACL, timestamps or external filesystem metadata after a removed/moved
file is recreated. Journals contain original file contents, stay local, and are
retained until deliberately removed. A pre-existing directory at the journal
location without the expected ownership marker is never adopted. If a process
was killed before returning its ID, inspect the journal subdirectories under that
root; no business operation begins before its journal exists.

Native-only alternative: write a JSON operation array using the native editor,
then run `plan --root <root> --request <operations.json> --output <new-plan.json>`
and `apply --plan <new-plan.json>`. Existing plan files are not overwritten.

## 中文

`ops_plan` 只预检并缓存计划。实际修改必须通过 Codex 原生 `exec_command`
运行返回的命令，沿用真实沙箱与审批；计划哈希和引用都不代表授权。
支持 write/edit/replace/copy/move/remove 六项操作，一批 1–32 个独立文件，
单文件 1 MiB、计划 8 MiB；源与目标不能重叠，父目录需已存在。文本修改要求
UTF-8；复制、移动、删除可处理二进制文件，不递归操作目录。

整批预检通过后，执行器先在根目录下保存原文恢复快照和日志，再逐项用原版
Rust worker 与精确版本校验发布。批次不是跨文件原子事务。失败或中断后先
查看 status，再显式 resume 或 rollback；禁止盲目重新 apply。恢复会检查当前
内容与计划前后状态，拒绝覆盖外部变更。rollback 可在中断后再次运行，但开始
回退后不能直接 resume 向前执行。

回退保证文件内容与存在状态，不承诺重建已删除文件的原 ACL、时间戳等元数据。
日志包含原始文件内容，仅保存在本机，直到明确清理。若进程在返回 ID 前终止，
可在该根目录的 `.codex-ops-mutations` 子目录中找到已持久化的日志。

## Native read-only plan loading

The native CLI reads a quiescent cache through a bounded read-only snapshot; it does
not initialize SQLite or create WAL files in the source cache. An active cache writer
can make the reference temporarily unavailable before execution. This is a read failure,
not a reason to rerun a possibly completed change.

The worker preserves existing file metadata. Some Windows workspace-write sandboxes
permit ordinary writes but deny the ownership/ACL operations required for that
publication. Such requests remain denied and the journal records inspection status.
Use an already-permitted native editor when suitable; the plugin never changes
permissions or silently falls back to a less restrictive executor.
