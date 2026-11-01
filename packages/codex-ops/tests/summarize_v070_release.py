"""Derive a payload-free, non-promotional cost summary without changing release gates."""
import argparse
import hashlib
import json
from pathlib import Path


def change(old,new):
    return 100*(new/old-1) if old else None


def outer_summary(report,audit):
    lookup={r['key']:r for r in report['reports']};pairs={}
    availability={a:{'observedAttempts':0,'unavailableAttempts':0} for a in ('v061','v070')}
    for trial in audit['trials']:
        row=lookup[trial['key']];available=trial['outerCalls']['available']
        availability[trial['condition']]['observedAttempts' if available else 'unavailableAttempts']+=1
        if available:pairs.setdefault((row['task'],row['repeat']),{})[row['condition']]=trial
    paired=[value for value in pairs.values() if len(value)==2]
    results={}
    for label,selected in [('allObservedPairs',paired),('commonSuccessfulObservedPairs',[p for p in paired if all(t['passed'] for t in p.values())])]:
        totals={arm:{'exec':sum(p[arm]['outerCalls']['exec'] for p in selected),
                     'wait':sum(p[arm]['outerCalls']['wait'] for p in selected)} for arm in ('v061','v070')}
        results[label]={'pairs':len(selected),'totals':totals,
                        'execChangePercent':change(totals['v061']['exec'],totals['v070']['exec'])}
    return {'availability':availability,**results,
            'scope':'Exact first main-model-turn raw calls only; native oracle events excluded. Initial unobserved rows are not zero.'}


def development_summary(report,first):
    known={key:0 for key in ('inputTokens','cachedInputTokens','uncachedInputTokens','outputTokens','totalTokens')}
    for totals in report['developmentConsumption'].values():
        for key in ('inputTokens','cachedInputTokens','uncachedInputTokens','outputTokens'):known[key]+=totals.get(key,0)
    known['totalTokens']=known['inputTokens']+known['outputTokens']
    for group in first['groups'].values():
        usage=group['knownUsageLowerBound']
        for key in ('inputTokens','cachedInputTokens','outputTokens','totalTokens'):known[key]+=usage.get(key,0)
        known['uncachedInputTokens']+=usage.get('inputTokens',0)-usage.get('cachedInputTokens',0)
    completed=len(report['reports'])+len(report['excludedInvalidFixtureAttempts'])+first['attemptStates'].get('recorded_completed_attempt',0)
    return {'recordedCompletedAttempts':completed,'interruptedAttempts':first['attemptStates'].get('interrupted_or_unsettled',0),
            'knownUsageLowerBound':known,
            'excludedInvalidProducerAttempts':len(report['excludedInvalidFixtureAttempts']),
            'unknownUsage':'Unreported in-flight usage from first interrupted attempt remains unknown.',
            'scope':'Comparable composite + original invalid LF producer attempts + first stopped candidate. Retained rows counted once.'}


def build(report,audit,first):
    assert report['complete'] and len(report['reports'])==72,'Wait for complete composite dataset'
    assert audit['reportComplete'] and len(audit['trials'])==72,'Audit must cover same completed dataset'
    assert {r['key'] for r in report['reports']}=={r['key'] for r in audit['trials']}
    metrics=report['summary'];all_attempts=metrics['allAttempts'];common=metrics['commonSuccessfulPairs']
    comparisons={}
    for name,groups in [('allAttempts',all_attempts),('commonSuccessfulPairs',common)]:
        comparisons[name]={key:change(groups['v061'][key],groups['v070'][key]) for key in
                           ('observedActions','inputTokens','cachedInputTokens','uncachedInputTokens','outputTokens')}
    return {'version':'0.7.0','measurementStatus':'completed mixed-cohort evaluation; not installation or release approval',
            'model':report['model'],'effort':report['effort'],'compositeCohorts':True,
            'retainedNonLongAttempts':len(report['reusedAttemptKeys']),
            'newContinuationAttempts':len(report['reports'])-len(report['reusedAttemptKeys']),
            'allAttempts':all_attempts,'commonSuccessfulPairs':common,'changesPercent':comparisons,
            'medianPairedInputReduction':metrics['medianPairedInputReduction'],
            'outerCalls':outer_summary(report,audit),
            'workflowUse':audit['groups'],
            'frozenTargetStatus':{**metrics['targetStatus'],'presentationInducedRetrievalReduction':audit['targetStatus']},
            'presentationInducedRetrieval':{'reduction':audit['displayInducedReduction'],'status':audit['targetStatus'],
                                          'reason':'Uses direct model-visible evidence and manual labels; unresolved cases and zero baseline remain UNKNOWN.'},
            'strictFailures':[{'condition':r['condition'],'task':r['task'],'repeat':r['repeat']} for r in report['reports'] if not r['outcome']['passed']],
            'baselineSuccessCandidateFailurePairs':metrics['baselineSuccessCandidateFailurePairs'],
            'developmentConsumption':development_summary(report,first),
            'releaseGatePassed':metrics['releaseGatePassed'],
            'limitations':['Native actions, outer calls and internal worker launches are different metrics.',
              'No dollar billing conversion or general workload/speed claim.',
              'Whole-run outer counts unavailable for initial 12 attempts; observed subset reported separately.',
              'Workflow counts in controlled prompts are not everyday or eligible-opportunity adoption rates.',
              'Wall time includes host.run setup, excludes fixture preparation and native oracle; instrumentation changes I/O overhead.',
              'Original producer failures and interrupted first-round cost remain retained; no outcome or threshold is regraded.']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',type=Path,default=Path('verification/v070-costs-combined.json'))
    parser.add_argument('--audit',type=Path,default=Path('verification/v070-combined-tool-audit-final.json'))
    parser.add_argument('--first-audit',type=Path,default=Path('verification/v070-first-usage-audit.json'))
    parser.add_argument('--output',type=Path,default=Path('verification/v070-release-cost-summary.json'))
    args=parser.parse_args()
    inputs=[args.report,args.audit,args.first_audit]
    result=build(*(json.loads(path.read_text(encoding='utf-8')) for path in inputs))
    result['evidenceSha256']={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    assert not args.output.exists(),'Retain previous summary; choose a new output filename'
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('allAttempts','changesPercent','frozenTargetStatus','releaseGatePassed')},indent=2))


if __name__=='__main__':main()
