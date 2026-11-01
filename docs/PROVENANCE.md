# Source provenance / 源码来源

Codex Ops derives from the MIT-licensed dsh-ops repository by T-Auto and contributors.
`native/` remains the shared file/document worker dependency; its crate and binary names
are retained for compatibility. `packages/codex-ops/` is the current Codex adaptation.
The root LICENSE, the plugin LICENSE and historical third-party notices are preserved.

The standalone extraction is a normal commit on PR #8: no commit history was rewritten.
DSH TypeScript components, shell distribution packages, npm release machinery and old Codex
development snapshots were removed from the current index. They remain accessible in the
parent commits. Existing local copies were left untracked to preserve installation paths.
Portable packages contain current plugin source and required binaries, not those snapshots.

Codex Ops 源自 T-Auto 及贡献者以 MIT 许可发布的 dsh-ops。`native/` 保留必要的文件和文档
worker，内部 crate 与二进制名称保持兼容；当前 Codex 适配位于 `packages/codex-ops/`。
根目录和插件许可证、历史第三方声明均保留。

独立化通过 PR #8 的普通提交完成，不重写历史。DSH TypeScript 组件、shell 分发包、npm
发布流程和旧 Codex 开发快照从当前索引移除，仍可通过父提交访问。本机副本保留为未跟踪文件，
避免破坏已有安装路径。便携包只包含当前插件源码和必要二进制，不包含旧快照。
