# Codex Ops

This repository owns the Codex MCP plugin in `packages/codex-ops/`, not the DSH host plugin.
Read [CONTRIBUTING](docs/CONTRIBUTING.md) for build and validation commands.
The current plugin's contracts are in [its README](packages/codex-ops/README.md).

## Boundaries

- `native/` is the retained MIT-licensed dsh-ops worker dependency. Preserve its attribution
  and crate/worker identities unless changing the dependency contract intentionally.
- `packages/codex-ops/rust-kernel/` depends on `native/`. Build both before integration tests.
- Python runtime, hooks, bridge and packaging live in `packages/codex-ops/`.
- Older development snapshots may exist locally but are untracked. They are not production
  sources; retrieve historical versions from Git when needed. Preserve local installation paths.
- Native/model output and Code Mode program values are distinct projections. Compression
  must preserve exact raw recovery, program values, errors, media and execution state.
- Preserve path authority, permission checks, revision checks, paging and completeness.
  POSIX directory operations use opened-directory identity authorization: external renames
  preserve authority over that directory, while symlink replacement must not redirect effects.
  Windows retains parent rename exclusion. Test both contracts without hiding failures.

## Changes and verification

- Keep every tracked code file at most 1000 lines. Run `npm run check:size`.
- Keep implementation slices around 1000 added lines; tests and byte-identical moves are
  excluded. PR #8 also includes the user-requested standalone repository extraction.
- Every new behavior needs an assertion that fails when reverted. Platform-only tests may
  explicitly skip on other systems; report skip counts and reasons. A skip is not a pass.
- Build outputs, virtual environments and generated runtime files are not edited or committed.
- Use English in code and commits; update user documentation in English and Chinese together.
  Add behavior and shipped documentation changes to `docs/CHANGELOG.md`.
- New dependencies need a reason, an exact version published at least seven days earlier,
  and no weakened security configuration.
- Use conventional imperative commit subjects and the user's identity, without AI attribution.
  Link the issue, name changed scope and include actual validation counts in the PR.
- Preserve pushed history. Merge only with maintainer authorization and passing required checks.

## Environment

Use PowerShell for Windows Git and npm commands. When testing through WSL, set
`UV_PROJECT_ENVIRONMENT` to a Linux-only path outside the checkout before invoking uv;
otherwise uv can replace the Windows `.venv`.
Keep tests and installations isolated from the user's active Codex home and trusted hooks.

For engineering skill integration, use [issue tracking](docs/agents/issue-tracker.md),
[triage labels](docs/agents/triage-labels.md), and [domain guidance](docs/agents/domain.md).
