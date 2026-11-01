"""Export a self-contained, interactive, payload-free statistics snapshot."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time

from store import default_root, MAX_STORE, TTL
import telemetry


def _empty_cache():
    return {'available': False, 'liveReferences': 0, 'liveBytes': 0, 'quotaBytes': MAX_STORE,
            'ttlSeconds': TTL, 'counters': {}}


def _cache_snapshot(path, now):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=0.25)) as db:
        db.execute('BEGIN')
        count, size = db.execute('SELECT COUNT(*),COALESCE(SUM(size),0) FROM observations WHERE created>=?',
                                 (now - TTL,)).fetchone()
        counters = dict(db.execute('SELECT key,value FROM metrics'))
        return {**_empty_cache(), 'available': True, 'liveReferences': count, 'liveBytes': size, 'counters': counters}


def cache_snapshot(root, now):
    try:
        path = Path(root) / 'observations.sqlite3'
        if path.is_file():
            return _cache_snapshot(path, now)
    except (OSError, sqlite3.Error):
        pass
    return _empty_cache()


def collect(origin='production', root=None):
    now = time.time()
    selected = default_root() if root is None else Path(root)
    presentation = telemetry.snapshot(origin, selected)
    newest = max((instance['updatedAt'] for instance in presentation['instances']), default=None)
    return {'schemaVersion': 1, 'generatedAt': now, 'newestSampleAt': newest,
            'origin': origin, 'presentation': presentation, 'cache': cache_snapshot(selected, now)}


def _script_json(value):
    encoded = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
    for source, escaped in (('<', '\\u003c'), ('>', '\\u003e'), ('&', '\\u0026')):
        encoded = encoded.replace(source, escaped)
    return encoded


def render(value):
    return HTML.replace('__SNAPSHOT__', _script_json(value))


def export(output, origin='production', root=None):
    target = Path(output)
    if not target.is_absolute() or target.suffix.lower() != '.html':
        raise ValueError('output must be an absolute .html file path')
    value = collect(origin, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(value), encoding='utf-8')
    return {'output': str(target), 'origin': origin, 'generatedAt': value['generatedAt'],
            'presentationAvailable': value['presentation']['available'], 'networkRequired': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='Absolute .html export path')
    parser.add_argument('--origin', choices=('production', 'validation'), default='production')
    parser.add_argument('--store', help='Optional existing local Codex Ops data directory')
    args = parser.parse_args(argv)
    print(json.dumps(export(args.output, args.origin, args.store), ensure_ascii=False))


HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
<title>Codex Ops · 输出观察台</title>
<style>
:root{font-family:"Segoe UI Variable","Segoe UI","Microsoft YaHei",sans-serif;color:#183147;background:#f1f5f8;font-synthesis:none;font-size:15px;--navy:#183147;--cyan:#087e91;--orange:#b7551f;--muted:#576d7c;--line:#d5e0e7}
*{box-sizing:border-box}body{margin:0}button,input,select{font:inherit}button,select{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #008da6;outline-offset:3px}
header{padding:25px max(24px,calc((100vw - 1180px)/2));display:flex;align-items:center;justify-content:space-between;background:var(--navy);color:white;gap:20px}header strong{font-size:20px;font-weight:650}header span{color:#b6d2df;font-size:13px}.origin{padding:5px 12px;border:1px solid #648292;border-radius:20px;color:white}
main{max-width:1228px;padding:42px 24px 60px;margin:auto}h1{margin:0;font-size:35px;font-weight:650;letter-spacing:-1px}h2{font-size:21px;margin:0 0 16px;font-weight:650}p{line-height:1.7}p.sub{color:var(--muted);margin:10px 0 22px;max-width:74ch}.metadata{font-size:13px;color:var(--muted);margin-bottom:24px;display:flex;gap:18px;flex-wrap:wrap}
.workspace{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(270px,1fr);gap:28px;margin-bottom:30px}.flow{background:white;border-radius:14px;padding:28px 30px 26px;border:1px solid var(--line)}.flow-head{display:flex;justify-content:space-between;gap:20px;align-items:baseline;margin-bottom:26px}.flow-head h2{margin:0}.saving{color:var(--cyan);font-size:20px;font-weight:650;font-variant-numeric:tabular-nums}.bar-row{display:grid;grid-template-columns:78px 1fr;gap:14px;align-items:center;margin-top:18px}.bar-label{font-size:13px;color:var(--muted)}.track{background:#eef3f6;border-radius:5px;height:35px;position:relative;overflow:hidden}.fill{height:100%;min-width:0;background:#7993a5}.fill.after{background:var(--cyan)}.bytes{position:relative;display:block;text-align:right;font-size:17px;font-weight:650;margin-top:6px;font-variant-numeric:tabular-nums}.note{font-size:12px;line-height:1.7;color:var(--muted);margin:22px 0 0;max-width:76ch}.readback{padding:23px 0 6px}.readback h2{color:var(--orange)}.metrics{margin:0}.metrics div{display:flex;justify-content:space-between;align-items:baseline;gap:16px;padding:12px 0;border-bottom:1px solid var(--line)}dt{font-size:14px;color:var(--muted)}dd{margin:0;font-size:19px;font-weight:600;font-variant-numeric:tabular-nums}.mini{font-size:12px;color:var(--muted)}.status{padding:14px 18px;border-left:4px solid var(--cyan);background:#e3f0f2;margin:0 0 28px;line-height:1.7;font-size:13px}.status.empty{border-color:var(--orange);background:#f7ebdf}
.panel{background:white;padding:25px 28px;border:1px solid var(--line);border-radius:12px;margin-top:24px}.panel-head{display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap}.panel-head h2{margin:0}.controls{display:flex;gap:8px;flex-wrap:wrap}input,select{background:#fff;border:1px solid #bdccd6;color:var(--navy);padding:9px 11px;border-radius:6px}input{width:215px}.table-wrap{overflow:auto;margin-top:20px}table{border-collapse:collapse;width:100%;font-size:13px;text-align:right}th{border-bottom:2px solid var(--line);padding:0;color:var(--muted);font-weight:500;white-space:nowrap}th:first-child,td:first-child{text-align:left}th button{width:100%;text-align:inherit;background:none;border:0;color:inherit;padding:11px 13px}td{padding:13px;border-bottom:1px solid #edf1f4;font-variant-numeric:tabular-nums}td:first-child{max-width:440px;overflow-wrap:anywhere}tbody tr:hover{background:#f2f8fa}.row-empty{text-align:center!important;color:var(--muted);padding:30px}footer{margin-top:27px;color:var(--muted);font-size:12px;line-height:1.8}summary{cursor:pointer;font-weight:600;color:var(--navy)}details{margin-top:20px}#cache{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.7 "Segoe UI",sans-serif}.noscript{padding:24px;background:#fff3df}
@media(max-width:760px){header{padding:20px}header span{display:none}main{padding:28px 16px}h1{font-size:29px}.workspace{grid-template-columns:1fr;gap:8px}.flow,.panel{padding:22px 18px}.readback{padding:18px 4px}.panel-head{align-items:flex-start}.controls{width:100%}input{min-width:0;flex:1}.bar-row{grid-template-columns:65px 1fr}.metadata{gap:6px}.flow-head{align-items:flex-start}.saving{font-size:17px}}
</style></head><body>
<header><strong>Codex Ops</strong><span>输出观察台</span><div class="origin" id="origin"></div></header>
<main><h1>输出去了哪里</h1><p class="sub">把压缩前后的呈现量、原文回读和来源放在一起看，判断哪些优化减少了实际交互成本。</p>
<div class="metadata"><span id="generated"></span><span id="sample-age"></span></div>
<noscript><p class="noscript">此本地快照需要 JavaScript 来显示和筛选统计。它不连接网络。</p></noscript>
<div class="workspace"><section class="flow" aria-labelledby="flow-title"><div class="flow-head"><h2 id="flow-title">呈现输出</h2><span class="saving" id="saving"></span></div>
<div class="bar-row"><span class="bar-label">压缩前</span><div><div class="track"><div class="fill" id="before-bar"></div></div><span class="bytes" id="before"></span></div></div>
<div class="bar-row"><span class="bar-label">压缩后</span><div><div class="track"><div class="fill after" id="after-bar"></div></div><span class="bytes" id="after"></span></div></div>
<p class="note" id="items"></p></section>
<section class="readback" aria-labelledby="readback-title"><h2 id="readback-title">原文回读成本</h2><dl class="metrics"><div><dt>成功检索返回</dt><dd id="retrieval-bytes"></dd></div><div><dt>重复页返回</dt><dd id="repeat-bytes"></dd></div><div><dt>成功检索次数</dt><dd id="retrieval-items"></dd></div></dl><p class="note">这里统计 ops_result 返回值的字节；它可能随后经过呈现，不与左侧相加或相减。重复页指相同检索请求，并不一定是浪费。</p></section></div>
<p class="status" id="coverage"></p>
<section class="panel" aria-labelledby="output-title"><div class="panel-head"><h2 id="output-title">呈现来源</h2><div class="controls"><select id="group" aria-label="呈现分组"><option value="byTool">按工具</option><option value="bySession">按会话标识</option><option value="byReason">按处理原因</option><option value="byChannel">按输出通道</option></select><input id="filter" type="search" aria-label="筛选呈现来源" placeholder="筛选来源…"></div></div><div class="table-wrap"><table id="outputs"><thead><tr></tr></thead><tbody></tbody></table></div></section>
<section class="panel" aria-labelledby="retrieval-title"><div class="panel-head"><h2 id="retrieval-title">回读对应的结果来源</h2><div class="controls"><select id="retrieval-group" aria-label="回读分组"><option value="byTool">按工具</option><option value="bySession">按会话标识</option></select><input id="retrieval-filter" type="search" aria-label="筛选回读来源" placeholder="筛选来源…"></div></div><div class="table-wrap"><table id="retrievals"><thead><tr></tr></thead><tbody></tbody></table></div><p class="note">已关联的引用归于产生结果的工具／会话；未关联记录使用可证明的调用来源，缺少证据时显示“未归因”。</p></section>
<footer>统计口径：UTF-8 字节，不是模型 token、净上下文节省或任务成功率。数据来自保留期内累计记录；旧版记录不能追溯归因。此文件是导出时的快照，重新运行导出命令以更新。<details><summary>查看缓存状态与测量说明</summary><p id="cache"></p><p id="measurement"></p></details></footer>
</main><script id="snapshot" type="application/json">__SNAPSHOT__</script><script>
'use strict';
const snapshot=JSON.parse(document.getElementById('snapshot').textContent);
const p=snapshot.presentation,t=p.totals,r=p.retrievalCosts;
const el=id=>document.getElementById(id);
const number=value=>Number(value||0).toLocaleString('zh-CN');
const bytes=value=>{const n=Number(value||0),a=Math.abs(n);if(a<1024)return number(n)+' B';if(a<1048576)return (n/1024).toFixed(1)+' KiB';return (n/1048576).toFixed(2)+' MiB';};
const put=(id,value)=>{el(id).textContent=value;};
put('origin',snapshot.origin==='production'?'日常使用':'验证数据');
put('generated','导出于 '+new Date(snapshot.generatedAt*1000).toLocaleString('zh-CN'));
put('sample-age',snapshot.newestSampleAt===null?'暂无样本':('最近样本距导出 '+number(Math.max(0,Math.round(snapshot.generatedAt-snapshot.newestSampleAt)))+' 秒'));
put('before',bytes(t.originalBytes));put('after',bytes(t.presentedBytes));
put('saving',t.originalBytes?((100*t.savedBytes/t.originalBytes).toFixed(1)+'% '+(t.savedBytes>=0?'减少':'变化')):'等待样本');
const scale=Math.max(t.originalBytes,t.presentedBytes,1);
el('before-bar').style.width=(100*t.originalBytes/scale)+'%';el('after-bar').style.width=(100*t.presentedBytes/scale)+'%';
put('items',number(t.items)+' 段文字；减少 '+bytes(t.savedBytes)+'。包含已呈现的检索页，排除非文字协议帧。');
put('retrieval-bytes',bytes(r.returnedBytes));put('repeat-bytes',bytes(r.repeatedPageBytes));put('retrieval-items',number(r.items));
const attribution=p.attributionCoverage;
put('coverage',p.available?('工具归因 '+number(attribution.toolAttributedItems)+' / '+number(t.items)+' 段；会话标识归因 '+number(attribution.sessionAttributedItems)+' / '+number(t.items)+' 段。未归因记录保留在总数中。会话标识是匿名散列，不等于完整聊天统计。'):'尚未产生统计。通过启用 Codex Ops 的会话使用工具后，再导出此快照。');
if(!p.available)el('coverage').classList.add('empty');
put('cache',snapshot.cache.available?('有效引用 '+number(snapshot.cache.liveReferences)+'；缓存 '+bytes(snapshot.cache.liveBytes)+' / '+bytes(snapshot.cache.quotaBytes)+'；保留 '+number(snapshot.cache.ttlSeconds/3600)+' 小时。'):'缓存尚不可用；此导出没有创建或清理缓存。');
put('measurement',p.measurement+'\n'+p.retrievalMeasurement);
const label=value=>value==='unattributed'?'未归因':value;
function table(id,selectId,filterId,source,columns){
 let sort=columns[columns.length-1].key,ascending=false;
 const node=el(id),head=node.querySelector('thead tr'),body=node.querySelector('tbody');
 function draw(){
  const query=el(filterId).value.toLocaleLowerCase(),group=source[el(selectId).value]||{};
  const rows=Object.entries(group).map(([key,value])=>({label:key,...value})).filter(row=>label(row.label).toLocaleLowerCase().includes(query));
  rows.sort((a,b)=>{const result=sort==='label'?a.label.localeCompare(b.label):Number(a[sort])-Number(b[sort]);return ascending?result:-result;});
  body.replaceChildren();
  for(const row of rows){const tr=document.createElement('tr');for(const column of columns){const td=document.createElement('td');td.textContent=column.key==='label'?label(row.label):column.bytes?bytes(row[column.key]):number(row[column.key]);tr.append(td);}body.append(tr);}
  if(!rows.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=columns.length;td.className='row-empty';td.textContent=query?'没有匹配的来源':'暂无记录';tr.append(td);body.append(tr);}
  for(const th of head.children)th.setAttribute('aria-sort',th.dataset.key===sort?(ascending?'ascending':'descending'):'none');
 }
 for(const column of columns){const th=document.createElement('th'),button=document.createElement('button');th.dataset.key=column.key;button.type='button';button.textContent=column.title;button.addEventListener('click',()=>{ascending=sort===column.key?!ascending:false;sort=column.key;draw();});th.append(button);head.append(th);}
 el(selectId).addEventListener('change',draw);el(filterId).addEventListener('input',draw);draw();
}
table('outputs','group','filter',p,[{key:'label',title:'来源'},{key:'items',title:'段数'},{key:'originalBytes',title:'压缩前',bytes:true},{key:'presentedBytes',title:'压缩后',bytes:true},{key:'savedBytes',title:'减少量',bytes:true}]);
table('retrievals','retrieval-group','retrieval-filter',r,[{key:'label',title:'来源'},{key:'items',title:'次数'},{key:'returnedBytes',title:'返回字节',bytes:true},{key:'repeatedPageItems',title:'重复页次数'},{key:'repeatedPageBytes',title:'重复页字节',bytes:true}]);
</script></body></html>'''


if __name__ == '__main__':
    main()
