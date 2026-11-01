# Environment and quality / 环境与质量

Python is pinned to 3.14.3 in `.python-version`. `pyproject.toml` declares exact
direct dependencies and preserves the validated transitive constraints; `uv.lock`
locks the complete resolution and artifact hashes. New packages use a seven-day
release cutoff. This Windows-only adapter does not install into global Python.

Python 固定为 3.14.3。`pyproject.toml` 声明精确直接依赖及已验证的传递依赖约束，
`uv.lock` 锁定完整解析与安装包哈希；新增包设置七天发布截止限制，不安装到全局环境。

- Production / 生产：`C:/Users/imsfp/.local/share/codex-runtimes/codex-ops-uv`
  runs MCP, hooks and the gRPC bridge. It contains 30 runtime packages, without
  coverage, Radon or Lizard. 运行 MCP、hooks 和桥接，共 30 个运行依赖，不含质量测量工具。
- Development / 开发：the package's `.venv` includes runtime dependencies plus the
  pinned `dev` group. 项目内 `.venv` 包含运行依赖与锁定的 dev 组。
- The two previous `python -m venv` environments are retained for rollback of older
  plugin/runtime versions. They were already isolated from global site-packages.
  原先两个 `python -m venv` 环境本来就与全局依赖隔离；保留它们供旧版回退。

From this package directory / 在本包目录执行：

```powershell
uv sync --locked --python C:\Python314\python.exe
uv run --locked python scripts/measure_quality.py
```

Production sync / 生产同步（单独 PowerShell 进程中执行，避免后续开发命令复用该变量）：

```powershell
$env:UV_PROJECT_ENVIRONMENT = "$env:USERPROFILE\.local\share\codex-runtimes\codex-ops-uv"
uv sync --locked --no-dev --python C:\Python314\python.exe
```

The measured suite has 219 automated tests, eight baseline/bridge app-server
scenarios and three instrumented native shim cases. Additional release validation
runs ten staged-runtime cases against the actual MSIX status directory and checks
MCP capture/retrieval round trips with the production Python. No external model is used.

测量包含 219 项自动化测试、8 项 app-server 对照场景和 3 项带覆盖率采集的原生启动器
场景。发布额外验证实际 MSIX 状态目录的 10 项运行时场景，以及生产 Python 下的 MCP
保存与完整取回。全部使用固定本地响应，不调用外部模型。

## CRAP methodology / CRAP 口径

`CC² × (1 − coverage)³ + CC`, with `coverage` in [0,1]. The original author's
investigation threshold is **>30**. There is no meaningful single project CRAP score:
report the function distribution and specific hotspots.

This project additionally enforces the user's stricter **maximum 6** for every
measured function, including new private functions and methods. The gate checks the
unrounded score, with the same formula, coverage definition and module inventory.

公式为 `CC² × (1 − coverage)³ + CC`，coverage 为 0–1；沿用原作者 **>30** 的排查阈值。
它是函数级指标，报告分布和具体热点，不把平均值当成整个项目的质量证明。
本项目额外执行用户要求的 **所有函数 ≤6**，包含新增私有函数和方法，按未四舍五入的
分数验收。计算公式、覆盖率定义和测量模块清单保持不变。

The 0.2.3 architecture pass keeps the existing public interfaces. Observation paging
owns its cursor/projection/budget rules internally; hook eligibility, native execution
proof, lifecycle ownership and presentation decoding each retain their rules locally.
Behavioral tests cross the existing interfaces; Windows registry/launch adapters are
controlled in tests without changing the user's registry or opening another Desktop.

0.2.3 保留原有对外 interface，将游标、投影和预算集中在观察结果分页的内部职责中；
hook 资格、原生执行证据、生命周期和呈现解析也各自保持规则的 locality。测试通过原有
interface 验证行为，Windows 注册表与启动 adapter 在测试中受控，不修改用户配置。

- Python CC uses Radon 6.0.1. Coverage uses coverage.py 7.16.2, counting executed
  statements and branch opportunities. This is an explicit proxy for the original
  basis-path coverage, not identical to all CRAP implementations.
- Scope is 32 Python production/installation modules, including nested functions
  exactly once. Tests, the old stdio bridge and the uninstalled restart helper are
  excluded. `experimental/presentation.py` is included because production imports it.
- Native subprocesses are measured with test-only 100 ms snapshots. Windows Job
  termination can miss final unsaved lines. No instrumentation enters production.
- Rust shim CC uses Lizard 1.17.31. No Rust execution coverage is available, so its
  CRAP remains null, rather than assuming either zero or full coverage. Upstream
  dsh-ops Rust worker code and the unmodified OpenAI host are outside this adapter audit.

Python 用 Radon 测复杂度、coverage.py 测语句和分支机会覆盖，作为原始基础路径覆盖率
的近似。范围为 17 个生产/安装模块，嵌套函数不重复计数；不计测试、旧 stdio 桥接及
未安装的重启助手。生产实际导入的 presentation 模块计入。子进程快照仅用于测试。
Rust 启动器只有复杂度，没有执行覆盖率，因此 CRAP 留空；不把上游 worker 或 OpenAI
原生 host 冒充本插件自身的测量结果。

Outputs / 产物：`verification/quality/crap.md`, `crap.json`, `coverage.json` and
`instrumented-host.json`. JSON includes source hashes to identify the measured code.

0.3 also runs `uv run --locked python tests/run_workload_benchmark.py`: four fixed
real-tool trajectories using repository reads/search, batch inspection and actual
tests. It checks byte counts, unchanged values and exact reference reconstruction.
This is not a real-model/token/task-quality A/B; correctness-only full retrieval
costs are reported separately in `verification/workload-benchmark.json`.
0.3 另有四条固定真实工具轨迹：源码读取/搜索、批量检查、实际测试；核对输出字节、
原值与引用重建。这不是模型 token 或任务质量 A/B，正确性验证的全量回读成本单独报告。

Sources / 来源：[original CRAP definition](https://testing.googleblog.com/2011/02/this-code-is-crap.html),
[uv locking and sync](https://docs.astral.sh/uv/concepts/projects/sync/),
[coverage subprocess measurement](https://coverage.readthedocs.io/en/7.16.2/subprocess.html).

## 0.4 release / 0.4 发布

The final deterministic gate measures 325 functions across 32 Python modules: maximum
CRAP 6, zero above 6, 98.72% statement-plus-branch coverage. All new mutation, telemetry,
retrieval, preview and dashboard functions are included. Five MCP tools are discovered
by a real stdio client; planning leaves files unchanged until native CLI apply.

最终确定性验收覆盖 32 个 Python 模块、325 个函数，CRAP 最高 6、超过 6 为 0，
语句与分支覆盖率 98.72%。新增修改、统计、检索、预览和面板函数均纳入。
真实 stdio 客户端发现五个 MCP 工具；计划生成后文件保持原样，原生 CLI 才执行修改。

The separate real-model pilot is invoked with tests/run_model_benchmark.py --run
--shim PATH. Its report records actual tokens, time and independent outcome checks;
one controlled task does not establish general savings. See verification/real-model-benchmark.json
when present. It is separate from the deterministic quality gate above.

真实模型试验由独立脚本显式启动，记录实际 token、耗时和独立结果检查；单个受控任务
不能证明普遍收益。报告存在时见 verification/real-model-benchmark.json，与上述确定性门禁分开。
