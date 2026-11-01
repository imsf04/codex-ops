# 文件参数

调用 `ops_files(root, operation, args)`。根目录必须是已有绝对目录，参数中的路径
相对根目录解析且不得越界。原版 Rust worker 拒绝链接、重解析点及常见凭证文件名。
这是本地 MCP 只读能力，不是 Codex 每轮 shell 沙箱的实现。

| operation | args 示例 |
|---|---|
| read | `{"files":[{"path":"src/main.ts","offset":1,"limit":200}]}` |
| grep | `{"path":".","pattern":"error","glob":["*.ts"],"limit":100,"exactTotal":false}` |
| glob | `{"path":".","pattern":["*.ts"],"limit":100}` |
| stat | `{"path":"src/main.ts"}` |
| diff | `{"path":"src/main.ts","content":"proposed content\n","offset":0,"limit":100}` |

read 支持 1–32 个文件，行号从 1 开始；搜索偏移从 0 开始。grep 使用 Rust 正则，
可设置 caseInsensitive、beforeContext、afterContext（0–32）及 outputMode
（content、files_with_matches、count、summary）。遵守 scanComplete、pageComplete、
truncatedBy、continuation、nextOffset 与每个文件的覆盖信息。stat 可以成功返回
exists:false；diff 只比较传入字符串，不写文件。

适配器保存 worker 已返回的内容，最多 128 KiB。引用完整不等于原文件或搜索覆盖完整。
获取新内容时缩小查询或遵循 worker continuation；已有内容通过 ops_result 检索。
