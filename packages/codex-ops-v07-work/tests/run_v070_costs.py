"""Frozen, tool-neutral 72-attempt 0.6.1/0.7.0 comparison. No execution without --run."""
import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

import run_v06_model_benchmark as harness
from v070_model_tasks import TASKS, prepare_task, evaluate_task

ROOT = Path(__file__).resolve().parents[1]
COMMON = '\nFor every native command explicitly set workdir to the absolute fixture directory. Use no network or downloads.\n'
ARMS = ('v061', 'v070')
FAMILY_MAPPING = {
    'symbol-definition-and-callers': {'tasks':['code_location'],'limits':'Find definition/regression; arbitrary complete call graph not claimed'},
    'configuration-precedence-with-distractor': {'tasks':['configuration_order']},
    'chinese-question-with-and-without-code-anchor': {'tasks':['chinese_anchor','chinese_domain'],'limits':'No-anchor domain phrase exists in Chinese documentation; opaque absent vocabulary uses deterministic needs_anchor test'},
    'medium-source-output-exact-recovery': {'tasks':['medium_exact_source'],'limits':'Exact source answer; byte-perfect transport gate remains deterministic'},
    'multi-document-contradictory-evidence': {'tasks':['conflicting_documents','document_lookup_tariff']},
    'late-log-error-coverage': {'tasks':['late_log']},
    'multi-reference-relevance-and-batch': {'tasks':['conflicting_documents'],'limits':'Task does not force reference creation or batch use; reference protocol is a separate deterministic gate'},
    'changed-source-index-invalidation': {'tasks':['source_revised_during_task'],'limits':'Validates final source after explicit change; no forced index means index invalidation also requires deterministic gate'},
    'native-test-failure-to-source': {'tasks':['repair_tests_config']},
    'long-task-terminal-and-access-denied': {'tasks':['long_command_failure'],'limits':'Terminal exit is tested; access denied and polling scheduling require deterministic native gate'},
    'resume-with-changed-source': {'tasks':['resume_partial_work'],'limits':'Resumes explicit partial files, not a process restart; restart/stale reference protocol tested separately'},
    'multi-agent-cost-and-opportunity-attribution': {'tasks':[],'limits':'Not covered by single-agent model harness; separate real multi-agent attribution gate required'}
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def configuration(version, package):
    quality = json.loads((package/'verification/quality/crap.json').read_text())
    bundle = Path(os.environ['LOCALAPPDATA'])/'CodexOps/runtime'/version
    receipt = json.loads((bundle/'bundle.json').read_text())
    script = 'import hook,json; hook.runtime_status.current=lambda:{"activeForThisProcess":True}; print(json.dumps(hook._session_start()))'
    hook = json.loads(subprocess.check_output([sys.executable,'-c',script],cwd=package,text=True,encoding='utf-8'))
    skill = package/'skills/compact-output/SKILL.md'
    guidance = hook['hookSpecificOutput']['additionalContext']
    source = ast.parse((package/'server.py').read_text(encoding='utf-8'))
    count = sum(isinstance(decorator,ast.Call) and isinstance(decorator.func,ast.Attribute) and decorator.func.attr=='tool'
                for node in source.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) for decorator in node.decorator_list)
    return {'executable':str(bundle/'bin/codex-ops-cli.exe'),'package':str(package),'toolCount':count,
            'instructions':'Installed compact-output skill:\n'+skill.read_text(encoding='utf-8')+'\nActive SessionStart guidance:\n'+guidance+
                '\nSkill references resolve under '+str(skill.parent)+'.'+COMMON,
            'sourceSha256':quality['sourceSha256'],'stagedSha256':receipt['files'],'skillSha256':digest(skill)}


def verify(config):
    for base, hashes in ((Path(config['package']),config['sourceSha256']),
                         (Path(config['executable']).parents[1],config['stagedSha256'])):
        for name, expected in hashes.items():
            assert digest(base/name)==expected, 'Source or immutable runtime changed: '+str(base/name)


def schedule():
    result=[]
    for repeat in range(1,4):
        for index,task in enumerate(TASKS):
            order=ARMS if (repeat+index)%2 else tuple(reversed(ARMS))
            result.extend({'key':f'{repeat}-{task}-{arm}','task':task,'repeat':repeat,'condition':arm} for arm in order)
    return result


def native_evaluate(host, task, workspace, expected):
    payload={key:value for key,value in expected.items() if key!='spec'}
    encoded=base64.b64encode(json.dumps(payload).encode()).decode()
    command=[str(Path(sys.base_prefix)/'python.exe'),'-I',str(ROOT/'tests/native_v070_oracle.py'),
             '--task',task,'--root',str(workspace),'--expected',encoded]
    result=host.request('command/exec',{'command':command,'cwd':str(workspace),'timeoutMs':30000},timeout=45)
    if result['exitCode']:
        return {'passed':False,'checks':0,'evaluationBlocked':True,'error':result['stderr'][-2000:]}
    return {**json.loads(result['stdout']),'evaluationSandbox':'native configured workspace-write'}


def actions(row):
    return sum(row.get('completedItemsByType',{}).get(k,0) for k in ('commandExecution','mcpToolCall','fileChange'))


def totals(rows):
    usage=[(r.get('tokens') or {}).get('total',{}) for r in rows]
    inputs=sum(x.get('inputTokens',0) for x in usage)
    cached=sum(x.get('cachedInputTokens',0) for x in usage)
    times=sorted(r['wallSeconds'] for r in rows if 'wallSeconds' in r)
    return {'attempts':len(rows),'passed':sum(r['outcome']['passed'] for r in rows),
            'observedActions':sum(actions(r) for r in rows),'inputTokens':inputs,'cachedInputTokens':cached,
            'uncachedInputTokens':inputs-cached,'outputTokens':sum(x.get('outputTokens',0) for x in usage),
            'modelUsageMissingAttempts':sum(not bool(r.get('tokens')) for r in rows),
            'medianWallSeconds':statistics.median(times) if times else None,
            'p95WallSeconds':times[max(0,(95*len(times)+99)//100-1)] if times else None,
            'retrievalCalls':sum(sum(n for t,n in r.get('completedMcpTools',{}).items() if t.endswith('.ops_result')) for r in rows)}


def reduction(old,new,key):
    return 1-new[key]/old[key] if old[key] else None


def summarize(rows):
    groups={arm:[r for r in rows if r['condition']==arm] for arm in ARMS}
    all_totals={arm:totals(group) for arm,group in groups.items()}
    pairs=[];common={arm:[] for arm in ARMS}
    for old in groups['v061']:
        new=next((r for r in groups['v070'] if (r['task'],r['repeat'])==(old['task'],old['repeat'])),None)
        if new is None:continue
        both=old['outcome']['passed'] and new['outcome']['passed']
        eligible=bool(old.get('eligibleForComparison') and new.get('eligibleForComparison'))
        pair={'task':old['task'],'repeat':old['repeat'],'bothPassed':both,'eligible':eligible,
              'baselinePassed':old['outcome']['passed'],'candidatePassed':new['outcome']['passed']}
        if eligible:
            pair['inputReduction']=reduction(totals([old]),totals([new]),'inputTokens')
        if both and eligible:
            common['v061'].append(old);common['v070'].append(new)
        pairs.append(pair)
    matched={arm:totals(group) for arm,group in common.items()}
    old,new=matched['v061'],matched['v070']
    targets={'actionsReduction':reduction(old,new,'observedActions'),'inputReduction':reduction(old,new,'inputTokens'),
             'uncachedInputNonIncreasing':new['uncachedInputTokens']<=old['uncachedInputTokens'] if common['v061'] else None,
             'presentationInducedRetrievalReduction':None}
    complete=len(rows)==72 and all(p['eligible'] for p in pairs) and len(pairs)==36
    target_status={key:'UNKNOWN' for key in ('actionsReduction','inputReduction','uncachedInputNonIncreasing','presentationInducedRetrievalReduction')}
    if complete and common['v061']:
        target_status['actionsReduction']='PASS' if targets['actionsReduction']>=0.25 else 'FAIL'
        target_status['inputReduction']='PASS' if targets['inputReduction']>=0.20 else 'FAIL'
        target_status['uncachedInputNonIncreasing']='PASS' if targets['uncachedInputNonIncreasing'] else 'FAIL'
    return {'allAttempts':all_totals,'commonSuccessfulPairs':matched,'pairs':pairs,'targets':targets,
            'targetStatus':target_status,
            'baselineSuccessCandidateFailurePairs':[{'task':p['task'],'repeat':p['repeat']} for p in pairs if p['baselinePassed'] and not p['candidatePassed']],
            'medianPairedInputReduction':statistics.median(p['inputReduction'] for p in pairs if p.get('inputReduction') is not None)
                if any(p.get('inputReduction') is not None for p in pairs) else None,
            'complete':len(rows)==72,'releaseGatePassed':False,
            'gateReason':'Protocol/multi-agent gates and causally labelled immediate retrieval are separate; this report alone never claims release acceptance.'}


def execution_observed(row):
    if row['task']!='long_command_failure':return
    found=False
    for line in Path(row['eventsPath']).read_text(encoding='utf-8').splitlines():
        event=json.loads(line);item=event.get('params',{}).get('item',{})
        if item.get('type')=='commandExecution' and 'run_probe.py' in json.dumps(item.get('command','')):
            found=found or item.get('exitCode')==7
    row['requiredExecutionObserved']=found
    if not found:
        row['outcome']={**row['outcome'],'passed':False,'executionEvidenceMissing':'native run_probe.py terminal exit 7'}


def stop_at_pair_boundary(stop_file, completed):
    return stop_file is not None and completed % 2 == 0 and Path(stop_file).exists()


def resume_report(destination, configs, model, effort):
    report=json.loads(destination.read_text(encoding='utf-8'))
    assert report.get('interrupted') and not report.get('complete'), 'Resume requires a graceful stopped report'
    assert report.get('activeAttempt') is None and len(report['reports']) % 2 == 0, 'Never retry an interrupted paid attempt'
    assert report['model']==model and report['effort']==effort, 'Resume must retain model and effort'
    assert report['configurations']==configs, 'Resume must retain exact source/runtime/guidance'
    assert report['schedule']==schedule(), 'Resume must retain the original schedule'
    for name,expected in report['evaluationSourceSha256'].items():
        assert digest(ROOT/'tests'/name)==expected, 'Evaluation source changed; use a new round: '+name
    assert digest(ROOT/'verification/v070-acceptance-design.json')==report['acceptanceSha256']
    report.setdefault('interruptions',[]).append({key:report.get(key) for key in ('stoppedAt','stopReason','stoppedAfterAttempts')})
    report.update(interrupted=False,resumedAt=time.time())
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--model',default='gpt-6.1-terra')
    parser.add_argument('--effort',default='medium',choices=('low','medium','high','xhigh'))
    parser.add_argument('--timeout',type=int,default=300)
    parser.add_argument('--report',default='verification/v070-costs-final.json')
    parser.add_argument('--stop-file',type=Path,help='Gracefully stop before the next pair when this file exists')
    parser.add_argument('--resume',action='store_true',help='Continue only unstarted pairs in an unchanged gracefully stopped run')
    args=parser.parse_args()
    acceptance=json.loads((ROOT/'verification/v070-acceptance-design.json').read_text())
    assert len(TASKS)==12 and set(FAMILY_MAPPING)==set(acceptance['families'])
    if not args.run:
        print(json.dumps({'paidCalls':0,'plannedAttempts':72,'tasks':TASKS,'familyMapping':FAMILY_MAPPING,'acceptance':acceptance},indent=2))
        return
    destination=ROOT/args.report
    assert args.resume or not destination.exists(),'Retain every paid attempt; choose a distinct report for a different candidate'
    configs={'v061':configuration('0.6.1',ROOT.parent/'codex-ops'),'v070':configuration('0.7.0',ROOT)}
    for config in configs.values():verify(config)
    harness.prepare_task=prepare_task;harness.evaluate_task=evaluate_task;harness.native_evaluate=native_evaluate
    original_flags=harness.mcp_flags
    harness.mcp_flags=lambda package,store:original_flags(package,store)+['-c','model_reasoning_effort='+json.dumps(args.effort)]
    previous=resume_report(destination,configs,args.model,args.effort) if args.resume else None
    root=Path(previous['root']) if previous else Path(tempfile.mkdtemp(prefix='codex-ops-v070-costs-'))
    (root/'workspaces').mkdir(exist_ok=True)
    report={'version':'0.7.0','model':args.model,'effort':args.effort,'root':str(root),'startedAt':time.time(),
            'configurations':configs,'acceptance':acceptance,'familyMapping':FAMILY_MAPPING,'schedule':schedule(),
            'reports':[],'complete':False,'limitations':['Single-agent trials; multi-agent attribution needs separate gate.',
             'Version-specific skills and SessionStart text are injected eagerly, not actual on-demand skill loading.',
             'Outer functions.exec counts are not reliably emitted by this host; native action metric is separate.',
             'No dollar-price conversion; cumulative input includes cached input. No failure replacements.',
             'Immediate display-induced retrieval needs separate labelled evidence; total retrieval count is not a substitute.']}
    report['evaluationSourceSha256']={name:digest(ROOT/'tests'/name) for name in
        ('run_v070_costs.py','v070_model_tasks.py','native_v070_oracle.py','model_tasks.py','model_task_variants.py',
         'run_v06_model_benchmark.py','run_model_benchmark.py')}
    report['acceptanceSha256']=digest(ROOT/'verification/v070-acceptance-design.json')
    if previous:report=previous
    report['stopFile']=str(args.stop_file.resolve()) if args.stop_file else None
    def save():
        report['summary']=summarize(report['reports'])
        destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    retained={row['key'] for row in report['reports']}
    for item in report['schedule']:
        if item['key'] in retained:continue
        if stop_at_pair_boundary(args.stop_file,len(report['reports'])):
            report.update(interrupted=True,stoppedAt=time.time(),stopReason='stop-file observed at pair boundary',
                          stoppedAfterAttempts=len(report['reports']),activeAttempt=None)
            save();break
        report['activeAttempt']=item['key'];save()
        try:
            row=harness.trial(root,item,configs[item['condition']],args.model,args.timeout)
            execution_observed(row)
        except Exception as exc:
            row={**item,'outcome':{'passed':False,'checks':0},'error':repr(exc),'eligibleForComparison':False,
                 'tokens':None,'workspace':str(root/'workspaces'/item['key']),
                 'eventsPath':str(root/'workspaces'/(item['key']+'.events.jsonl'))}
        report['reports'].append(row);report['activeAttempt']=None;save()
        print(json.dumps({'key':row['key'],'passed':row['outcome']['passed'],'actions':actions(row)}),flush=True)
    for config in configs.values():verify(config)
    for name,expected in report['evaluationSourceSha256'].items():
        assert digest(ROOT/'tests'/name)==expected,'Evaluation/oracle source changed during paid run: '+name
    assert digest(ROOT/'verification/v070-acceptance-design.json')==report['acceptanceSha256']
    complete=len(report['reports'])==len(report['schedule'])
    report.update(complete=complete,endedAt=time.time())
    if complete:report['interrupted']=False
    save()


if __name__=='__main__':
    main()
