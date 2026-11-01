# Contributing to Codex Ops

[中文](贡献指南.md)

The current source is `packages/codex-ops/`; the shared Rust worker is `native/`.
Use Python 3.14, uv 0.11.32 and Rust 1.97.1 as pinned in CI. Node 24 runs repository
checks and downloads the pinned Codex host used only in integration tests.

From the repository root:

```console
npm ci --ignore-scripts
npm run check:size
cargo test --workspace --locked --manifest-path native/Cargo.toml
cargo build --locked --release --manifest-path native/Cargo.toml --bin dsh-ops-worker
cargo test --locked --manifest-path packages/codex-ops/rust-kernel/Cargo.toml
cargo build --locked --release --manifest-path packages/codex-ops/rust-kernel/Cargo.toml
```

Copy the resulting worker and kernel to `packages/codex-ops/bin/`, retaining `.exe` on
Windows. Windows also builds the launcher with `rustc --edition 2024 -O
packages/codex-ops/runtime_bridge/shim.rs -o packages/codex-ops/bin/codex-ops-cli.exe`.
Then, from `packages/codex-ops/`:

```console
uv sync --locked
uv run --locked python -m unittest discover -s tests
```

Integration tests require the native Codex CLI/host pinned by CI. The workflow prepares
those fixtures and tests extracted packages in an isolated Codex home. Follow
`.github/workflows/ci.yml` for the complete four-platform procedure. Report passes, failures
and platform-specific skips separately. POSIX directory failures currently block acceptance.

For WSL, set `UV_PROJECT_ENVIRONMENT` outside this checkout so Linux uv does not replace
the Windows virtual environment. Preserve existing user installations when testing.

Open a linked issue, update bilingual docs and `CHANGELOG.md`, and submit the PR template.
Keep code files under 1000 lines; keep implementation slices around 1000 added lines.
Never rewrite pushed history. Old DSH sources and development snapshots are available through
Git history, not part of current builds. Required native attribution remains in LICENSE/NOTICE.
