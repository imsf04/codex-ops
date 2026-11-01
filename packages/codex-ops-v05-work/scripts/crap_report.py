"""Function-level CRAP estimate using Radon CC and measured statement/branch coverage."""
import hashlib
import json
from pathlib import Path
import statistics
import argparse

import lizard
from radon.complexity import cc_visit

ROOT = Path(__file__).resolve().parents[1]
FILES = ['files.py', 'hook.py', 'reducers.py', 'runtime_status.py', 'server.py',
         'structured.py', 'telemetry.py', 'progress.py', 'presentation_policy.py',
         'shell_receipt.py', 'store.py', 'experimental/presentation.py',
         'runtime_bridge/control.py', 'runtime_bridge/grpc_relay.py',
         'runtime_bridge/manager.py', 'runtime_bridge/projection.py', 'runtime_bridge/wire.py']
FILES += ['telemetry_details.py', 'dashboard.py', 'bridge_context.py', 'frame_dedup.py',
          'record_preview.py', 'retrieval_views.py', 'observation_metrics.py']
FILES += sorted(str(path.relative_to(ROOT)).replace('\\', '/') for path in (ROOT / 'mutations').glob('*.py'))
FILES += ['query_workflow.py', 'catalog.py', 'semantic_preview.py', 'telemetry_windows.py',
          'task_snapshot.py', 'dashboard_server.py', 'query_aggregates.py', 'result_batch.py']
FILES += ['query_preview.py']
FILES += ['cache_reader.py']
FILES += ['readonly_snapshot.py']


def crap(complexity, coverage):
    if complexity < 1 or not 0 <= coverage <= 1:
        raise ValueError('Expected positive complexity and coverage fraction in [0,1]')
    return complexity ** 2 * (1 - coverage) ** 3 + complexity


def functions(source):
    found = {}
    def visit(block, prefix=''):
        if hasattr(block, 'methods'):
            for method in block.methods:
                visit(method)
            return
        name = prefix + block.fullname
        found[(block.lineno, name)] = (name, block)
        for child in block.closures:
            visit(child, name + '.')
    for block in cc_visit(source):
        visit(block)
    return list(found.values())


def main(max_crap=None):
    directory = ROOT / 'verification/quality'
    coverage = json.loads((directory / 'coverage.json').read_text(encoding='utf-8'))
    measured = {name.replace('\\', '/'): value for name, value in coverage['files'].items()}
    rows, hashes = [], {}
    counts = dict(covered_lines=0, num_statements=0, covered_branches=0, num_branches=0)
    for name in FILES:
        source = (ROOT / name).read_text(encoding='utf-8')
        hashes[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        data = measured[name]
        for key in counts:
            counts[key] += data['summary'][key]
        for qualified, block in functions(source):
            # Exact function scope from coverage.py excludes nested function bodies.
            summary = data['functions'][qualified]['summary']
            total = summary['num_statements'] + summary['num_branches']
            covered = summary['covered_lines'] + summary['covered_branches']
            fraction = covered / total if total else 0.0
            rows.append({'file': name, 'line': block.lineno, 'function': qualified,
                         'complexity': block.complexity, 'coveragePercent': round(fraction * 100, 2),
                         'coveredOpportunities': covered, 'totalOpportunities': total,
                         'crap': crap(block.complexity, fraction)})
    rows.sort(key=lambda row: row['crap'], reverse=True)
    native = lizard.analyze_file(str(ROOT / 'runtime_bridge/shim.rs'))
    rust = [{'function': f.name, 'line': f.start_line, 'complexity': f.cyclomatic_complexity,
             'coveragePercent': None, 'crap': None} for f in native.function_list]
    rust.sort(key=lambda row: row['complexity'], reverse=True)
    report = {'formula': 'CC^2 * (1 - coverage)^3 + CC', 'threshold': '>30',
              'coverageDefinition': 'coverage.py statement + branch opportunities; proxy for original basis-path coverage',
              'scope': f'{len(FILES)} Python production/installation modules; no tests, legacy stdio prototype or uninstalled restart helper',
              'subprocessCoverage': 'Test-only 100ms snapshots; forced Job teardown can miss final unsaved lines',
              'rustLimitation': 'Rust shim complexity measured by Lizard; no Rust coverage instrumentation, therefore no Rust CRAP score',
              'functionCount': len(rows), 'above30': sum(row['crap'] > 30 for row in rows),
              'targetMaximum': 6, 'above6': sum(row['crap'] > 6 for row in rows),
              'median': round(statistics.median(row['crap'] for row in rows), 3),
              'maximum': rows[0]['crap'], 'coverage': counts, 'sourceSha256': hashes,
              'functions': rows, 'rustComplexityOnly': rust,
              'sources': ['https://testing.googleblog.com/2011/02/this-code-is-crap.html',
                          'https://radon.readthedocs.io/en/stable/api.html',
                          'https://coverage.readthedocs.io/en/7.16.2/subprocess.html',
                          'https://github.com/terryyin/lizard']}
    report['coveragePercent'] = round(100 * (counts['covered_lines'] + counts['covered_branches']) /
                                       (counts['num_statements'] + counts['num_branches']), 2)
    (directory / 'crap.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    lines = ['# Codex Ops CRAP report / CRAP 报告', '',
             f"Functions / 函数: {len(rows)}; CRAP > 6: {report['above6']}; CRAP > 30: {report['above30']}; median / 中位数: {report['median']}; max / 最大值: {report['maximum']}.",
             f"Measured statement + branch coverage / 实测语句与分支覆盖率: {report['coveragePercent']}%.", '',
             'CRAP = CC² × (1 − coverage)³ + CC. Requested maximum: 6; >30 remains the original investigation threshold.',
             '本项目要求所有函数 ≤6，使用未四舍五入的值验收；>30 是原作者的排查阈值。语句+分支覆盖率继续近似原公式的基础路径覆盖率，计算口径不变。', '',
             f'Scope: {len(FILES)} Python production/installation modules; tests, legacy stdio harness and the uninstalled restart helper are excluded.',
             f'范围：{len(FILES)} 个生产/安装 Python 模块；不计测试、旧 stdio 原型及未安装的重启助手。',
             'Native child processes use test-only 100 ms coverage snapshots; forced termination can miss final unsaved lines.',
             '原生子进程采用测试专用 100ms 覆盖率快照，强制退出可能漏掉最后未保存的执行行。', '',
             '| Function / 函数 | CC | Coverage / 覆盖率 | CRAP |', '|---|---:|---:|---:|']
    for row in rows:
        lines.append(f"| {row['file']}:{row['line']} `{row['function']}` | {row['complexity']} | {row['coveragePercent']}% | {row['crap']:.3f} |")
    lines += ['', '## Rust shim', '', 'Complexity only: no Rust coverage was measured, so CRAP is not fabricated.',
              '仅测复杂度：没有 Rust 覆盖率数据，不计算 CRAP，也不算入 Python 中位数。', '',
              '| Function / 函数 | CC |', '|---|---:|']
    lines += [f"| {row['function']}:{row['line']} | {row['complexity']} |" for row in rust]
    lines += ['', '## Sources / 来源', ''] + [f'- {url}' for url in report['sources']]
    (directory / 'crap.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('functionCount', 'above6', 'above30', 'median', 'maximum', 'coveragePercent')}))
    print(json.dumps(rows[:6]))
    if max_crap is not None and any(row['crap'] > max_crap for row in rows):
        raise SystemExit(f'CRAP exceeds requested maximum {max_crap}; see verification/quality/crap.md')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-crap', type=float)
    main(parser.parse_args().max_crap)
