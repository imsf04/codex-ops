# 按需操作契约

调用 `ops_catalog()` 获取简短目录，再用 `ops_catalog(operation="grep")` 取得
所选操作的精确 argsSchema、示例、执行入口和边界。示例中的已有绝对根目录是
占位符，执行前需要替换。

九类读取、只读 batch 和 search 走 ops_files；六类修改走 ops_plan。修改 schema
描述的是计划参数，而不是底层 Rust worker 参数：计划器计算版本并给出原生执行
入口。发现能力不执行修改或授予权限。尤其是计划 replace 使用 oldText、newText、
expectedCount，grep 才使用正则 pattern。

只读 batch 允许 1–4 项九类原生读取操作，不嵌套 batch、search 或修改。search
自己管理有界的两阶段流程，详见[搜索与上下文](query.zh-CN.md)。

Schema 可以识别常见类型和形状错误；原生语义检查仍然决定 PDF 编码是否支持、
权限是否允许、glob 是否含正向规则、版本是否匹配、精确编辑是否唯一。使用结果前
检查 status/error。参数错误时取得对应契约修正；搜索不完整时缩小范围；修改状态
不明时先检查审计状态。

这是通过 MCP 按需返回的参数文档，不声称动态注册 Codex 工具或替换宿主生成的 SDK。

English: [On-demand operation contracts](catalog.md)
