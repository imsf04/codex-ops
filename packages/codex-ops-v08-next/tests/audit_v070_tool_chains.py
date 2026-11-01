"""Extract bounded tool evidence for manual attribution; never infer causation from counts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from run_v070_observed import new_state, observe, summary

REF = re.compile(r'ops://[a-f0-9]{48}')
LABELS = {'display_missing_evidence','source_pagination_required','task_requires_full_content',
          'explicit_query_new_evidence','unknown'}


def read_events(path):
    if not path.exists():return []
    rows=[]
    for line_number,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        try:rows.append((line_number,json.loads(line)))
        except ValueError:pass
    return rows


def compact(item):
    result={'type':item.get('type'),'id':item.get('id')}
    if item.get('type')=='commandExecution':
        result.update(command=str(item.get('command',''))[:500],exitCode=item.get('exitCode'),
                      outputCharacters=len(item.get('aggregatedOutput') or ''))
    if item.get('type')=='mcpToolCall':
        args=item.get('arguments') or {}
        result.update(server=item.get('server'),tool=item.get('tool'),status=item.get('status'),
                      arguments={k:args[k] for k in ('operation','action','ref','view','offset','limit','max_bytes') if k in args})
    payload=item.get('result') if item.get('type')=='mcpToolCall' else item.get('aggregatedOutput')
    result['nativeResponseReferences']=list(dict.fromkeys(REF.findall(json.dumps(payload,ensure_ascii=False))))
    return result


def rollout_calls(paths, thread_ids):
    found=[p for p in paths if any(thread in p.name for thread in thread_ids)]
    if not found:return {'available':False,'reason':'No matching local rollout for ephemeral trial thread IDs','calls':None,'exec':None,'wait':None}
    seen=set();counts=Counter();output_refs={}
    for path in found:
        for _,event in read_events(path):
            payload=event.get('payload',{})
            if payload.get('type') in ('custom_tool_call','function_call'):
                key=payload.get('call_id')
                if key and key not in seen:
                    seen.add(key);counts[payload.get('name','unknown')]+=1
            if payload.get('type') in ('custom_tool_call_output','function_call_output'):
                refs=REF.findall(str(payload.get('output','')))
                if refs:output_refs[payload.get('call_id')]=list(dict.fromkeys(refs))
    return {'available':True,'rollouts':[str(p) for p in found],'calls':dict(counts),
            'exec':counts['exec'],'wait':counts['wait'],'modelVisibleOutputReferences':output_refs}


def native_raw_calls(events):
    state=new_state('audit','events')
    for _,event in events:observe(state,event)
    result=summary(state)
    if not result['observationAvailable']:return None
    references={}
    for item in result['outputs']:
        references.setdefault(item['callId'],[]).extend(item['references'])
    return {'available':True,'source':'native rawResponseItem/completed','mainThreadId':result['mainThreadId'],
            'mainTurnId':result['mainTurnId'],'calls':dict(Counter(x['name'] for x in result['calls'])),
            'exec':result['outerExec'],'wait':result['outerWait'],'modelVisibleOutputReferences':references,
            'excludedAfterMainTurn':result['excludedAfterMainTurn'],'excludedOtherTurn':result['excludedOtherTurn']}


def one_trial(row, rollouts, labels):
    path=Path(row['eventsPath']);events=read_events(path)
    thread_ids=set();native=[];workflows=Counter();retrievals=[];methods=Counter()
    main_finished=False;excluded_native_after_turn=0
    for line,event in events:
        methods[event.get('method','unknown')]+=1
        params=event.get('params',{});thread=params.get('threadId')
        if thread:thread_ids.add(thread)
        if event.get('method')=='turn/completed':main_finished=True
        item=params.get('item',{})
        if event.get('method')!='item/completed':continue
        if item.get('type') not in ('commandExecution','mcpToolCall','fileChange'):continue
        if main_finished:
            excluded_native_after_turn+=1;continue
        entry={'eventLine':line,**compact(item)}
        if item.get('type')=='mcpToolCall':
            args=item.get('arguments') or {}
            if item.get('tool')=='ops_workflow':workflows[args.get('operation','unknown')]+=1
            if item.get('tool')=='ops_result':
                key=row['key']+'/'+str(item.get('id',line))
                annotation=labels.get(key,{'label':'unknown','evidence':''})
                assert annotation['label'] in LABELS,key
                if annotation['label']!='unknown':assert annotation.get('evidence'), 'Human labels require cited event/rollout evidence'
                if annotation['label']=='display_missing_evidence':
                    assert all(annotation.get(k) for k in ('modelVisibleEvidence','evidenceNeed','whyAvoidable')), 'Positive causal labels require model-visible output, task need and avoidability evidence'
                queried=list(dict.fromkeys(REF.findall(json.dumps(args))))
                origins=[previous for previous in native if set(previous['nativeResponseReferences']) & set(queried)]
                retrievals.append({'caseId':key,'request':entry,'queriedReferences':queried,
                                   'previousNativeActions':native[-3:],'observedNativeReferenceOrigins':origins[-2:],
                                   'modelVisibleOriginProven':False,'annotation':annotation,
                                   'hint':'nonzero offset is compatible with necessary pagination, not proof of its cause' if args.get('offset',0) else 'raw first page alone does not prove avoidable retrieval'})
        native.append(entry)
    outer=native_raw_calls(events) or rollout_calls(rollouts,thread_ids)
    visible_refs=set()
    for refs in outer.get('modelVisibleOutputReferences',{}).values():visible_refs.update(refs)
    for case in retrievals:
        case['modelVisibleOriginProven']=bool(set(case['queriedReferences']) & visible_refs)
    return {'key':row['key'],'task':row['task'],'condition':row['condition'],'passed':row['outcome']['passed'],
            'eventsPath':str(path),'eventsSha256':hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
            'threadIds':sorted(thread_ids),'recordedMethods':dict(methods),'outerCalls':outer,
            'nativeActions':len(native),'excludedNativeActionsAfterMainTurn':excluded_native_after_turn,
            'workflowByOperation':dict(workflows),'retrievalCases':retrievals,
            'eligibleWorkflowOpportunity':'UNKNOWN: annotate the user task; do not divide workflow calls by all tools'}


def audit(report_path, rollout_root, annotations=None):
    report=json.loads(report_path.read_text(encoding='utf-8'));labels=annotations or {}
    rollouts=list(rollout_root.rglob('*.jsonl')) if rollout_root.exists() else []
    trials=[one_trial(row,rollouts,labels) for row in report['reports'] if row.get('eventsPath')]
    groups={}
    for arm in ('v061','v070'):
        selected=[t for t in trials if t['condition']==arm];counts=Counter();operations=Counter()
        for trial in selected:
            operations.update(trial['workflowByOperation'])
            counts.update(case['annotation']['label'] for case in trial['retrievalCases'])
        groups[arm]={'recordedTrials':len(selected),'tasksWithWorkflow':sum(bool(t['workflowByOperation']) for t in selected),
                     'workflowByOperation':dict(operations),'retrievalLabels':dict(counts),
                     'confirmedDisplayInduced':counts['display_missing_evidence'],'unknownRetrievals':counts['unknown'],
                     'eligibleOpportunityDenominator':None,'naturalAdoptionRate':None}
    unresolved=sum(g['unknownRetrievals'] for g in groups.values())
    complete=bool(report.get('complete')) and len(trials)==72
    baseline=groups['v061']['confirmedDisplayInduced'];candidate=groups['v070']['confirmedDisplayInduced']
    reduction=1-candidate/baseline if complete and not unresolved and baseline else None
    return {'sourceReport':str(report_path.resolve()),'reportComplete':complete,'groups':groups,'trials':trials,
            'displayInducedReduction':reduction,'target':0.5,
            'targetStatus':'UNKNOWN' if reduction is None else ('PASS' if reduction>=0.5 else 'FAIL'),
            'limitations':['Native command/MCP results are not proof of the outer functions.exec text seen by the model.',
              'Before observation-wrapper opt-in, the frozen host recorder retained no rawResponseItem output; later raw-enabled trials are explicitly distinguished.',
              'Outer counts use native raw call IDs first, matching local rollouts second; unavailable is not zero.',
              'Time proximity, raw view, or nonzero offset never establishes avoidable display-induced retrieval by itself.',
              'Manual labels require direct evidence; unknown cases remain unknown and block a point estimate.',
              'This artifact includes only bounded tool chains, not full user prompts or reasoning.']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('report',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--annotations',type=Path)
    parser.add_argument('--rollout-root',type=Path,default=Path.home()/'.codex/sessions')
    args=parser.parse_args();labels=json.loads(args.annotations.read_text()) if args.annotations else {}
    result=audit(args.report,args.rollout_root,labels)
    assert not args.output.exists(),'Retain previous audit; choose a new output filename'
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('reportComplete','groups','displayInducedReduction','targetStatus')},indent=2))


if __name__=='__main__':main()
