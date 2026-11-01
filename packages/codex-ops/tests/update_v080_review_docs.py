"""Record the final review state without changing release gates or installation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EN = '''## Model costs and adoption

**Final gate: FAIL; 0.7 remains installed.** The fresh evaluation completed all 132 attempts. `finalCandidate=true` identifies the measured source; `costGatePassed=false` and `releaseGatePassed=false` prevent promotion. [Final report](../verification/v080-cost-summary.json)

| Common-success comparison | Native actions | Outer calls | Input tokens | Uncached input | MCP worker starts |
|---|---:|---:|---:|---:|---:|
| Against 0.6.1, 31 pairs | −16.19% | −6.80% | −7.44% | −7.79% | +66.67% |
| Against 0.7, 43 pairs | −7.75% | −10.63% | −13.65% | −12.60% | −65.22% |

The required reductions against 0.6.1 remain 25% native actions and 20% input; both were missed. Uncached input improved, but strict quality non-regression also failed. Original pass counts are 33/36 (0.6.1), 45/48 (0.7), and 43/48 (0.8). These include three terminal-wrapper failures per arm. A separately preregistered wrapper correction passed 9/9 supplementary attempts; those results do not replace or merge into the original 132 or its gates. Two candidate late-log answers supplied log text where the fixed oracle required integer line 5001, despite that number being present in the delivered evidence. Both strict failures remain.

Explicit workflow selection is 26/48 (54.17%) for 0.8 versus 22/48 (45.83%) for 0.7. Candidate automatic delivery was observed in 3/48 tasks; the observed union is 29/48 (60.42%). Twelve save-only events are excluded. On the same legacy task set, candidate selection is 19/36 (52.78%) versus 8/36 (22.22%) for 0.6.1. Structural evidence observations are separate from task success. Baseline automatic instrumentation is unavailable, so absence is not zero. These are benchmark observations, not natural daily adoption; production adoption remains unknown.

The remaining costs come from concrete paths: Chinese-only questions can produce `needs_anchor`, domain labels can produce `no_match`, and tools are sometimes discovered in a separate model round despite same-exec guidance. Small tasks already use two calls and little output, leaving little compression benefit; native command batching varies between runs. The inherited diagnostic source-context parser also misreads an entire error prefix as part of a path in all three versions (identical source hashes). That pre-existing bug is separate from the new workflow's English-only automatic-anchor limitation and does not establish the cause of the strict answer-field failures. [Trace audit](../verification/v080-full-provisional-delivery-audit.md), [failure audit](../verification/v080-failure-audit-late-log-2.json)

Pilot, screening, complete-run and supplementary records remain separate. The screening win did not generalize to the full acceptance thresholds. Earlier invalid pilot consumption and failed outcomes are retained. No 0.7 waiver carries forward. A review can choose further optimization, or explicitly waive the failed gates for experimental activation with rollback; neither has been selected or executed here.

'''
ZH = '''## 模型成本与采用率

**最终门禁未通过；当前仍安装0.7。** 新鲜对照已完成132次尝试。`finalCandidate=true` 表示这份源码已经完成测量；`costGatePassed=false`、`releaseGatePassed=false` 保持禁止晋级。[最终报告](../verification/v080-cost-summary.json)

| 共同成功任务对照 | 原生动作 | 外层调用 | 输入token | 未缓存输入 | MCP进程启动 |
|---|---:|---:|---:|---:|---:|
| 对0.6.1，31对 | −16.19% | −6.80% | −7.44% | −7.79% | +66.67% |
| 对0.7，43对 | −7.75% | −10.63% | −13.65% | −12.60% | −65.22% |

对0.6.1要求原生动作减少25%、输入减少20%，两项都未达到；未缓存输入有所下降，但严格质量不回退也未通过。原始通过数为0.6.1的33/36、0.7的45/48、0.8的43/48，包含每组各3次终端包装器失败。预先登记、修正包装器后的独立补充测试9/9通过，不替换或并入原132次结果。0.8另有两次日志答案把正文填入要求整数5001的line字段；交付证据实际包含5001，仍按固定判定保留失败。

0.8显式工作流采用26/48（54.17%），0.7为22/48（45.83%）。0.8在3/48任务中观测到自动交付，合并覆盖29/48（60.42%）；12次仅保存事件不计服务。在同一旧任务集上，0.8为19/36（52.78%），0.6.1为8/36（22.22%）。证据结构计数不等于任务成功；旧版本没有对应自动交付插桩，不能把未观测当作零。这些是基准采用率，真实日常采用率仍未知。

剩余开销来自实际调用路径：纯中文问题可能返回needs_anchor，领域词不在源码中时返回no_match；即便已有同次发现并调用的提示，模型仍会单独发现工具。小任务原本只需两次调用且输出很短，压缩收益有限；模型合并原生命令的方式也存在波动。另有三版本共同继承的诊断来源路径解析错误：错误前缀被当作文件路径的一部分，源码哈希完全相同。它与新工作流仅自动提取英文锚点的缺口是两个问题，也不能直接断言它造成line字段失败。[轨迹审计](../verification/v080-full-provisional-delivery-audit.md)、[失败审计](../verification/v080-failure-audit-late-log-2.json)

试跑、筛选、全量和补充结果分别保留；筛选阶段收益没有在全量达到门槛。无效试跑消耗及失败记录未删除，0.7曾获例外不自动延续。下一步可选择继续优化，或明确接受未达门槛后实验启用并保留回退；本次尚未选择或执行安装。

'''


def update_release(name, heading, content):
    path = ROOT / 'docs' / name
    value = path.read_text(encoding='utf-8')
    start = value.index(heading)
    end = value.index('\n## ', start + len(heading))
    value = value[:start] + content + value[end + 1:]
    paragraphs = value.split('\n\n')
    paragraphs[2] = ('Status: final measured candidate; cost and strict quality gates failed. '
                     'Installed desktop remains 0.7.0. No experimental waiver or installation has occurred.'
                     if name.endswith('0.8.0.md') else
                     '状态：最终候选已测量，成本与严格质量门禁未通过。桌面仍启用0.7，尚无实验放行或安装。')
    path.write_text('\n\n'.join(paragraphs), encoding='utf-8')


def main():
    update_release('release-0.8.0.md', '## Model costs and adoption', EN)
    zh = ROOT / 'docs/release-0.8.0.zh-CN.md'
    headings = [line for line in zh.read_text(encoding='utf-8').splitlines() if line.startswith('## ')]
    update_release(zh.name, headings[2], ZH)
    for name in ('README.md', 'README.zh-CN.md'):
        path = ROOT / name
        value = path.read_text(encoding='utf-8')
        head, tail = value.split('\n', 1)
        notice = ('\n\n**Candidate only: final 132-attempt acceptance failed its cost and strict quality gates. '
                  '0.7 remains live; 0.8 has not been installed.** '
                  '[Final results / 最终结果](docs/result-0.8.0.zh-CN.md)\n'
                  if name == 'README.md' else
                  '\n\n**候选状态：132次完整验收的成本及严格质量门禁未通过，当前继续启用0.7，未安装0.8。** '
                  '[最终结果](docs/result-0.8.0.zh-CN.md)\n')
        value = head + notice + tail
        value = value.replace('This candidate is undergoing release acceptance.', 'Final acceptance is recorded; promotion remains blocked.')
        path.write_text(value, encoding='utf-8')
    path = ROOT / 'QUALITY.md'
    value = path.read_text(encoding='utf-8')
    marker = '## 0.8.0 candidate / 候选\n'
    notice = ('\nFinal cost gate FAIL: 132 attempts; common-success native/input reductions versus0.6.1 '
              '16.19%/7.44% (required25%/20%), versus0.7 7.75%/13.65%. Strict passes33/36,45/48,43/48 '
              '(0.6.1/0.7/0.8); separate terminal supplement9/9 does not replace original failures. '
              'Candidate explicit adoption26/48, observed explicit-or-automatic29/48; daily adoption unknown. '
              '`costGatePassed=false`, `releaseGatePassed=false`; installed0.7 unchanged. '
              '[Final report](verification/v080-cost-summary.json).\n\n'
              '最终成本门禁未通过，严格质量未达到不回退；补充测试单独保留，不替换全量结果。当前仍为0.7，'
              '0.8未安装；[完整中文结果](docs/result-0.8.0.zh-CN.md)。\n')
    value = value.replace(marker, marker + notice)
    value = value.replace('Fresh 132-attempt cost/adoption acceptance is still pending.', 'Fresh 132-attempt cost/adoption acceptance is complete and failed its gates.')
    path.write_text(value, encoding='utf-8')


if __name__ == '__main__':
    main()
