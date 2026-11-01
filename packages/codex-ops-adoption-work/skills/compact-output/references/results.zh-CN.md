# 缓存查询

English: [Cached queries](results.md).

查询只检查已保存的观察结果，不重新执行源工具。outline、find、items 与聚合
基于解码后的 MCP/inline 数据；raw 保留原始文字或 JSON。路径采用 RFC6901 JSON 指针。

一次调用可组合 1–8 项查询：

```json
{"action":"batch","max_bytes":12000,"requests":[
  {"ref":"ops://…","view":"find","query":"timeout","limit":5},
  {"ref":"ops://…","view":"count","path":"/records","query":"failed"},
  {"ref":"ops://…","view":"group","path":"/records","fields":["status"]}
]}
```

批次先验证全部分页参数，再查询；总字节预算在各项之间分配。每项保留独立错误、
扫描状态和续页位置。批次 complete 只说明所有请求已处理，不代表每页或原始来源完整。
释放引用仍是单独的单引用操作。

count 按记录进行字面筛选并计数。group 可统计标量记录，或指定对象记录的一个
顶层标量字段，缺失字段单列计数。最多扫描十万条记录、一千个分组，分组键最多
1024 个编码字节；遇到扫描截断应缩小 path/query。这些统计只覆盖保存的观察结果。

页面或批次 max_bytes 为 512–16000。批次需要为每项预留至少 512 字节及外层结构。
记录视图 limit 为 1–200；raw 使用 Unicode 字符偏移，忽略 limit。批次 path 最长
2048 字符、query 最长 200 字符、fields 最多 32 个名称，每个最长 256 字符。

显式分页和批量结果不会再次自动压缩。回读统计与随后呈现的字节可能重叠，不能
将两者相加冒充互不重叠的上下文成本。
