"""Read a retained benchmark and its traces without revising any trial outcome."""
import argparse
from collections import Counter
import json
from pathlib import Path


def trace(path):
    last_usage=None; usage_events=0; completed_turn=False; invalid_lines=0
    if not path.exists():
        return {'exists':False,'lastUsage':None,'usageEvents':0,'completedTurn':False,'invalidLines':0}
    for line in path.read_text(encoding='utf-8').splitlines():
        try:event=json.loads(line)
        except ValueError:
            invalid_lines+=1;continue
        if event.get('method')=='thread/tokenUsage/updated':
            last_usage=event['params']['tokenUsage'].get('total');usage_events+=1
        if event.get('method')=='turn/completed':completed_turn=True
    return {'exists':True,'lastUsage':last_usage,'usageEvents':usage_events,
            'completedTurn':completed_turn,'invalidLines':invalid_lines}


def audit(path):
    report=json.loads(path.read_text(encoding='utf-8'))
    root=Path(report['root']);recorded={r['key']:r for r in report['reports']}
    rows=[]
    for item in report['schedule']:
        key=item['key'];row=recorded.get(key)
        event_path=Path(row['eventsPath']) if row and row.get('eventsPath') else root/'workspaces'/(key+'.events.jsonl')
        details=trace(event_path)
        workspace=root/'workspaces'/key
        started=bool(row or details['exists'] or workspace.exists() or key==report.get('activeAttempt'))
        status='unstarted'
        if started:status='interrupted_or_unsettled'
        if row:status='recorded_completed_attempt'
        recorded_usage=(row.get('tokens') or {}).get('total') if row else None
        usage=details['lastUsage'] or recorded_usage
        rows.append({**item,'attemptState':status,'eventsPath':str(event_path),'trace':details,
                     'lastKnownUsage':usage,'recordedUsage':recorded_usage,
                     'recordTraceUsageDisagree':bool(recorded_usage and details['lastUsage'] and recorded_usage!=details['lastUsage']),
                     'usageComplete':bool(row and row.get('turnStatus')=='completed' and usage),
                     'usageSource':'last cumulative thread/tokenUsage/updated; report fallback only if missing trace'})
    groups={}
    for arm in ('v061','v070'):
        selected=[r for r in rows if r['condition']==arm]
        totals=Counter()
        for row in selected:totals.update(row['lastKnownUsage'] or {})
        groups[arm]={'attemptStates':dict(Counter(r['attemptState'] for r in selected)),
                     'knownUsageLowerBound':dict(totals),
                     'unknownOrPartialUsageAttempts':[r['key'] for r in selected if r['attemptState']!='unstarted' and not r['usageComplete']]}
    return {'sourceReport':str(path.resolve()),'sourceRoot':str(root),'activeAttemptAtStop':report.get('activeAttempt'),
            'plannedAttempts':len(rows),'attemptStates':dict(Counter(r['attemptState'] for r in rows)),
            'groups':groups,'attempts':rows,'limitations':[
                'Cumulative usage updates are not summed; each attempt contributes its latest observed total once.',
                'Usage for an interrupted/unsettled attempt is a lower bound; in-flight unreported tokens are unknown.',
                'Prepared/native-started does not prove the first model request completed.',
                'This is an additive audit, not an edit, regrade, retry or replacement of the retained report.']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('report',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=audit(args.report)
    assert not args.output.exists(),'Retain earlier audit; select a fresh output filename'
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('activeAttemptAtStop','plannedAttempts','attemptStates','groups')},indent=2))


if __name__=='__main__':main()
