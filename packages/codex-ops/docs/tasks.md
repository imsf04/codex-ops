# Staged native tasks

Codex Ops plans staged file and directory changes without writing the workspace.
The saved plan describes the complete sequence and binds the observed file revisions.
Execute its returned argv through Codex's native shell and current permission policy.
MCP planning grants no permission and never starts a worker or a scheduler.

`task_api.plan(root, stages, owner=None)` accepts an absolute existing root and 1–16
ordered stages. Each stage contains 1–32 `{operation, args}` entries; the whole task
contains at most 64 requested operations and 256 expanded primitives. Operations run
in the supplied order, including inside a stage. Stages are recovery checkpoints,
not atomic filesystem transactions. A later operation may depend on an earlier one.

The six file operations retain their existing argument shapes: `write`, `edit`,
`replace`, `copy`, `move`, `remove`. Directory operations are:

| Operation | Arguments | Preconditions |
| --- | --- | --- |
| `mkdir` | `{path}` | Parent exists at this point; target absent. |
| `rmdir` | `{path}` | Target is an empty directory. |
| `copy_tree` | `{path, to}` | Explicit source directory; absent, nonoverlapping destination. |
| `move_tree` | `{path, to}` | Verified copy followed by removal; not an atomic rename. |
| `remove_tree` | `{path}` | Explicit source directory; every captured descendant checked. |

Paths are normalized relative paths under the chosen root. Root itself, parent
traversal, links/reparse points, hard-linked files, credential paths, journal stores,
alternate streams, device names and ambiguous Windows spellings are rejected.
One spelling is required for each case-insensitive Windows path. Trees are bounded
to 128 nodes, 1 MiB per file and 8 MiB total captured contents. Tree publication does
not preserve directory ownership, ACLs or timestamps; rollback restores the observed
directory structure and file contents. The upstream file worker retains its metadata
checks and can report a permission or metadata failure after publishing bytes.

Example stages:

```json
[
  [{"operation":"mkdir","args":{"path":"review"}}],
  [{"operation":"copy","args":{"path":"src/a.txt","to":"review/a.txt"}}],
  [{"operation":"replace","args":{"path":"review/a.txt","oldText":"old","newText":"new","expectedCount":1}}]
]
```

Native task commands use `mutations/task_cli.py`:

```text
apply --plan-ref ops://…
status --root ABSOLUTE_ROOT --id TASK_ID
cancel --root ABSOLUTE_ROOT --id TASK_ID
resume --root ABSOLUTE_ROOT --id TASK_ID
rollback --root ABSOLUTE_ROOT --id TASK_ID
```

`apply` emits a `started` record containing the task ID before effects, then a final
receipt. Keep the normal shell session ID when it is still running. `cancel` requests
a cooperative stop before the next primitive; it does not kill a running worker.
Use native process controls when an immediate stop is intended. Explicit `resume`
clears the cancellation request. Rollback proceeds in reverse order and refuses to
remove unexpected files or replace externally changed contents.

Task journals live in `.codex-ops-tasks`; file primitives retain their individual
`.codex-ops-mutations` recovery journals. A parent records its child ID before file
effects. The current tree frontier is checked before each step. After a process exit,
status exposes whether the recorded frontier matches; an explicit recovery can
recognize one completed but uncheckpointed step without replaying it. Unknown or
partial effects stop with `needs-inspection` and expose the active child journal.
Never repeat `apply` after an uncertain result. Inspect the child and current paths,
then choose explicit resume or rollback.

For a tracked child stopped inside a move, explicit recovery verifies the untouched
parent paths and the exact child plan before delegating to its recovery journal.
Both resume and rollback handle a destination copied before the source was removed.
The requested recovery direction is persisted before effects; another interruption
can continue rollback without restarting forward execution. Conflicting child content
or changes elsewhere in the captured frontier remain blocked for inspection.

Dashboard summaries include both journal types under the same byte and entry limits.
They expose phases and counts, not a fresh verification of file postconditions.
Use native `status` for current postcondition checks. Explicit root/task IDs identify
workspace journals; they do not provide separate per-chat filesystem authorization.

## Directory authority by platform

Windows holds parent handles that exclude rename and reparse replacement during each directory
primitive. Linux and macOS use opened-directory identity authorization: each ancestor is opened
relative to the preceding descriptor with `O_DIRECTORY | O_NOFOLLOW`; `mkdir` and `rmdir` operate
relative to the held parent. A concurrent rename may relocate the authorized directory, including
outside its original pathname. The operation still affects that directory identity; a symlink
installed at the old pathname cannot redirect it. This is the approved POSIX contract, not a promise
to prevent other processes from renaming directories. Final-component symlinks are never followed.
Task frontier/revision checks still apply. If path changes prevent subsequent observation or
recovery, inspect the journals and actual locations; an error does not imply that no effects occurred.
