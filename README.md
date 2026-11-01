# Codex Ops

[English](README.en.md) · **中文**

为 Codex 提供紧凑证据读取、可恢复的大输出、文件与文档工具，以及分阶段文件任务的 MCP 插件。
Python 服务、原生 Rust worker、专用 Rust 内核和可选输出桥接共同组成插件。

## 状态与安装

当前版本为 **0.8.0 实验版本**。功能验证与成本指标分别记录；历史成本门槛未全部通过，
不将功能测试通过解释为已经达到节省 token 的目标。

跨平台构建与安装验收覆盖 Windows x64、Linux x64、macOS ARM64 和 macOS x64。
POSIX 目录任务采用目录身份授权；输出桥接的宿主与代理限制见安装指南。
下载 Actions 的平台预览产物后，按 [安装指南](packages/codex-ops/docs/portable-package.zh-CN.md)
安装并注册插件；预览包不等同于已发布的稳定版本。

## 源码

| 路径 | 内容 |
| --- | --- |
| `packages/codex-ops/` | 当前插件、Python 测试、hooks、桥接、安装与打包脚本 |
| `packages/codex-ops/rust-kernel/` | Codex Ops 专用 Rust 内核 |
| `native/` | 从 dsh-ops 保留的必要原生文件与文档 worker |
| `licenses/`、`LICENSE`、`NOTICE` | 许可证与来源说明 |
| `.github/workflows/ci.yml` | 四平台构建、安装运行验证与完整测试 |

详见 [插件工具与契约](packages/codex-ops/README.zh-CN.md)、
[贡献指南](docs/贡献指南.md)和 [变更记录](docs/CHANGELOG.md)。

## 来源与历史

项目起源于 dsh-ops 的 Codex 适配。当前 Git 树只保留 Codex Ops 和所需原生依赖；
DSH 产品层、npm 发布流程及旧版本开发快照保留在 Git 历史中。
原生 crate 和 worker 的 `dsh-ops` 名称是保留的内部依赖标识，不代表发布 DSH 插件。
历史提交未重写，原作者版权及 MIT 许可证保留。详见 [来源说明](docs/PROVENANCE.md)。
