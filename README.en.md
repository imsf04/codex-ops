# Codex Ops

**English** · [中文](README.md)

A Codex MCP plugin for compact evidence, recoverable large outputs, file and document tools,
and staged file tasks. It combines a Python service, a native Rust worker, a dedicated Rust
kernel, and an optional output bridge.

## Status and installation

Version **0.8.0 is experimental**. Functional validation and cost results are separate:
historical cost targets remain unmet. Passing functionality does not establish token savings.

Portable packages are under acceptance in PR #8 for Windows x64, Linux x64, macOS ARM64,
and macOS x64. POSIX directory tasks use directory identity authorization; host and proxy limitations of the
output bridge are documented in the [installation guide](packages/codex-ops/docs/portable-package.md).
Download the matching Actions preview artifact and follow that guide to install and register
the plugin. Preview artifacts are not stable releases.

## Source

| Path | Contents |
| --- | --- |
| `packages/codex-ops/` | Current plugin, Python tests, hooks, bridge, installation and packaging |
| `packages/codex-ops/rust-kernel/` | Dedicated Codex Ops Rust kernel |
| `native/` | Required file and document worker retained from dsh-ops |
| `licenses/`, `LICENSE`, `NOTICE` | License texts and attribution |
| `.github/workflows/ci.yml` | Four-platform builds, installed-runtime checks and full tests |

See the [plugin contracts](packages/codex-ops/README.md),
[contribution guide](docs/CONTRIBUTING.md), and [changelog](docs/CHANGELOG.md).

## Provenance

Codex Ops began as an adaptation of dsh-ops. The current tree contains Codex Ops and its
required native dependencies. The DSH product, npm release machinery and old development
snapshots remain in Git history. Internal `dsh-ops` crate and worker names identify retained
dependencies; this repository does not publish the DSH plugin. History and original MIT
copyright notices are preserved. See [provenance](docs/PROVENANCE.md).
