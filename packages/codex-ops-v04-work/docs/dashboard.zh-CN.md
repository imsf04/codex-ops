# 本地统计快照

通过生产 uv 环境导出一份独立 HTML 文件：

```powershell
& "$env:USERPROFILE/.local/share/codex-runtimes/codex-ops-uv/Scripts/python.exe" `
  "C:/Users/imsfp/code/dsh-ops/packages/codex-ops/dashboard.py" `
  --output "C:/Users/imsfp/Desktop/codex-ops-stats.html" --origin production
```

用浏览器打开这个文件。将 `--origin` 改为 `validation` 可查看测试统计。
`--store` 可选，用于指定其他已有的本地数据目录。导出路径必须是绝对 `.html`
路径；再次运行会替换指定文件。页面可离线使用，不启动服务器，不加载外部资源。

两个表格都支持筛选和排序。呈现来源可以按工具、会话匿名标识、处理原因和输出
通道分组。引用的生产来源明确时，回读归因到产生结果的工具／会话。缺少证据、
存在多个不同生产者及旧版记录保持“未归因”。会话标识代表已证明的运行时范围，
不一定等于一整个 Codex 聊天。

呈现统计记录压缩前后的 UTF-8 字节。回读统计单独记录成功 `ops_result` 返回的
字节；它们随后可能再次被呈现，因此页面不会将两者相加或相减来宣称净节省。
重复有界页请求不一定是无效工作。这些数据不衡量 token 或任务成功率。

导出时间与最近样本年龄说明这份静态快照的新鲜程度。保留的累计计数无法重建
精确的每日区间；重新导出即可更新。导出器使用只读 SQLite 事务读取缓存元数据，
不会读取保存的正文、创建缓存或清理过期引用。HTML 只包含聚合标签和匿名会话
散列，不包含保存的工具输出。

English: [Local statistics snapshot](dashboard.md).
