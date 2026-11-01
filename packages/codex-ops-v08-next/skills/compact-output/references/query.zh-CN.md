# 一次请求定位并读取上下文

使用 `ops_files(root, operation="search", args)` 搜索命中并读取附近源码。
root 必须是已有绝对目录；两个阶段都沿用原生路径、链接和凭据保护。

```json
{"path":"src","pattern":"def start","glob":["**/*.py"],"maxMatches":20,"maxFiles":4,"before":2,"after":5}
```

pattern 是非空 Rust 正则，最长 4096 字符。path 默认 `"."`；glob 为最多 32 项
非空字符串数组。caseInsensitive 为布尔值，默认 false。offset 为零起始搜索行
偏移，范围 0–1000000。maxMatches 为 1–64（默认 20），maxFiles 为 1–8（默认 4）；
before/after 为 0–20 行，默认各 3 行。未知字段和类型错误会被拒绝。

第一阶段由原版 worker 搜索，达到行数限制时提前停止；第二阶段按文件合并重叠
或相邻区间，一次读取最多 32 段。共享截止时间 45 秒，各阶段最多 22 秒，不自动重试。

判断不存在前先检查 search.scanComplete、search.nextOffset 和原生覆盖信息。
omittedMatches/omittedRanges 明确显示因选择上限遗漏的上下文；可缩小路径或提高
上限。context 保留原生区间、修订值、续读信息和逐文件错误。

搜索与读取不是原子文件快照。matchChecks 将选中的原始命中行与重新读取的正文
比较，返回 unchanged、changed 或 unavailable；只能发现命中行的变化，不能证明
文件其他部分不变。调查变化时同时保留原命中和较新的读取区间。被裁切或尚未读取
的上下文保持 partial。

通过 `ops_catalog(operation="search")` 按需取得精确参数 schema 和有效示例。
查询契约不执行操作，也不授予权限。

English: [Search and context](query.md)
