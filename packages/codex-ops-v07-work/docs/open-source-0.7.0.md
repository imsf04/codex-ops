# 0.7.0 reuse and provenance / 复用与来源

Date: 2026-10-30. No third-party source has been copied for this implementation.

SQLite FTS5 is used through Python's existing sqlite3 module. The deployed Python
runtime provides the engine; no extension download or new package is required.
An in-memory FTS5 query was executed in the development runtime before adoption.
SQLite is public domain: https://www.sqlite.org/copyright.html . Its first-party
FTS5 reference describes tokenization, MATCH and BM25:
https://www.sqlite.org/fts5.html .

本版直接使用已有 Python 运行时中的 SQLite FTS5，不复制其他项目索引源码，
不下载二进制扩展、不新增网络服务。已实际验证 FTS5 建表和 MATCH 查询可用。
开发环境及生产环境的具体版本与能力仍须分别验收。

Existing codex-ops native adapters, ownership, result batches and task journals
remain the implementation foundation. External projects in research-v07-github.md
inform interface choices only; their benchmark claims are not our results.
RTK's mixed licensing is a reason to avoid copying its newer engine/proxy code.
No package is introduced without an explicit provenance and dependency review.

现有原生适配器、引用所有权、批量查询与任务 journal 继续复用；调研项目仅提供
设计参考。本文不将第三方宣称的压缩比例当作本插件实测收益。
