"""Continue unstarted pairs with an explicit LF producer revision, retaining prior costs."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import time

import run_v070_costs as frozen
from run_v070_observed import instrument
from v070_fixture_continuation import prepare_task, REVISION
from v070_model_tasks import evaluate_task

ROOT=Path(__file__).resolve().parents[1]


def continuation_plan(source, source_path, observation_path=None):
    assert source.get('interrupted') and not source.get('complete'),'Stop source run gracefully before continuing'
    assert source.get('activeAttempt') is None and len(source['reports'])%2==0,'Retain in-flight attempt; do not retry it implicitly'
    source_hash=frozen.digest(source_path)
    retained=[];invalid=[]
    for original in source['reports']:
        row=copy.deepcopy(original)
        row['provenance']={'sourceReport':str(source_path.resolve()),'sourceReportSha256':source_hash,
                           'sourceKey':original['key'],'fixtureRevision':'v070.1-original'}
        row['cohort']='retained-original-final'
        if row['task']=='long_command_failure':
            row['exclusionReason']='Original producer writes platform-translated CRLF while frozen requiredFiles demands LF; original outcome is unchanged.'
            invalid.append(row)
        else:retained.append(row)
    schedule=copy.deepcopy(source['schedule'])
    for item in schedule:
        if item['task']=='long_command_failure':
            item['key']+='-'+REVISION;item['fixtureRevision']=REVISION
        else:item['fixtureRevision']='v070.1-original'
    retained_keys={r['key'] for r in retained}
    pending=[item for item in schedule if item['key'] not in retained_keys]
    assert len(schedule)==72 and len({r['key'] for r in schedule})==72
    assert len(retained)+len(pending)==72
    assert len(pending)%2==0
    for left,right in zip(pending[::2],pending[1::2]):
        assert (left['task'],left['repeat'])==(right['task'],right['repeat']) and left['condition']!=right['condition'], 'Continuation must preserve whole pairs'
    observed={}
    if observation_path and observation_path.exists():
        observed=json.loads(observation_path.read_text(encoding='utf-8')).get('observedAttempts',{})
    return {'schedule':schedule,'retained':retained,'excludedInvalidFixtureAttempts':invalid,'pending':pending,
            'priorKeysOuterUnavailable':[row['key'] for row in retained if row['key'] not in observed],
            'retainedObservedKeys':[row['key'] for row in retained if row['key'] in observed]}


def verify_source(source, path):
    for config in source['configurations'].values():frozen.verify(config)
    for name,expected in source['evaluationSourceSha256'].items():
        assert frozen.digest(ROOT/'tests'/name)==expected,'Frozen evaluation source changed: '+name
    assert frozen.digest(ROOT/'verification/v070-acceptance-design.json')==source['acceptanceSha256']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--source-report',type=Path,default=ROOT/'verification/v070-costs-final.json')
    parser.add_argument('--source-observation',type=Path,default=ROOT/'verification/v070-native-observation-sidecar.json')
    parser.add_argument('--report',type=Path,default=ROOT/'verification/v070-costs-combined.json')
    parser.add_argument('--observation-receipt',type=Path,default=ROOT/'verification/v070-continuation-observation.json')
    parser.add_argument('--stop-file',type=Path)
    parser.add_argument('--timeout',type=int,default=300)
    args=parser.parse_args()
    source=json.loads(args.source_report.read_text(encoding='utf-8'))
    plan=continuation_plan(source,args.source_report,args.source_observation)
    if not args.run:
        print(json.dumps({'paidCalls':0,'retainedAttempts':len(plan['retained']),
              'excludedInvalidFixtureAttempts':len(plan['excludedInvalidFixtureAttempts']),
              'newAttempts':len(plan['pending']),'combinedComparableAttempts':72,
              'fixtureRevision':REVISION,'pendingKeys':[x['key'] for x in plan['pending']]},indent=2));return
    assert not args.report.exists() and not args.observation_receipt.exists(),'Retain prior reports; choose fresh continuation artifacts'
    proof=ROOT/'verification/v070-fixture-lf-native-proof.json'
    producer_proof=json.loads(proof.read_text(encoding='utf-8'))
    assert producer_proof['revisedProducerSatisfiesFrozenBytes'] and producer_proof['revised']['execution']['exitCode']==7
    verify_source(source,args.source_report)
    configs=source['configurations'];model=source['model'];effort=source['effort']
    root=Path(tempfile.mkdtemp(prefix='codex-ops-v070-continuation-'));(root/'workspaces').mkdir()
    report={'version':'0.7.0','model':model,'effort':effort,'root':str(root),'startedAt':time.time(),
            'complete':False,'cohortDescription':'Composite paired dataset: retained non-long attempts plus new unstarted tasks and six revised-producer long attempts. Not one unchanged run.',
            'sourceReport':str(args.source_report.resolve()),'sourceReportSha256':frozen.digest(args.source_report),
            'sourceObservation':str(args.source_observation),'sourceObservationSha256':frozen.digest(args.source_observation) if args.source_observation.exists() else None,
            'producerProof':str(proof),'producerProofSha256':frozen.digest(proof),'fixtureRevision':REVISION,
            'fixtureRevisionScope':'Only generated run_probe.py write_text -> write_bytes and its expected protected hash. Frozen answer/required bytes/oracle/thresholds unchanged.',
            'configurations':configs,'acceptance':source['acceptance'],'familyMapping':source['familyMapping'],
            'schedule':plan['schedule'],'reports':plan['retained'],'reusedAttemptKeys':[r['key'] for r in plan['retained']],
            'excludedInvalidFixtureAttempts':plan['excludedInvalidFixtureAttempts'],
            'frozenEvaluationSourceSha256':source['evaluationSourceSha256'],
            'continuationSourceSha256':{name:frozen.digest(ROOT/'tests'/name) for name in
                 ('run_v070_continuation.py','v070_fixture_continuation.py','run_v070_observed.py')},
            'limits':source['limitations']+['This report combines explicit cohorts; earlier invalid producer attempts retain original outcomes and development cost.']}
    ledger={'instrumentationStartedAt':time.time(),'report':str(args.report),'wrapperSha256':frozen.digest(ROOT/'tests/run_v070_observed.py'),
            'priorKeysOuterUnavailable':plan['priorKeysOuterUnavailable'],'retainedObservedKeys':plan['retainedObservedKeys'],
            'retainedObservationReceipt':str(args.source_observation),'observedAttempts':{},
            'countBoundary':'Main model turn only; post-turn oracle events excluded.'}
    def save_observation():
        args.observation_receipt.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def save():
        report['summary']=frozen.summarize(report['reports'])
        all_cost_rows=report['reports']+report['excludedInvalidFixtureAttempts']
        report['developmentConsumption']={arm:frozen.totals([r for r in all_cost_rows if r['condition']==arm]) for arm in frozen.ARMS}
        report['developmentConsumptionScope']='This final/composite lineage only; earlier stopped first candidate has a separate usage audit and must also remain in overall development cost.'
        args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    frozen.harness.prepare_task=prepare_task;frozen.harness.evaluate_task=evaluate_task
    frozen.harness.native_evaluate=frozen.native_evaluate
    original_flags=frozen.harness.mcp_flags
    frozen.harness.mcp_flags=lambda package,store:original_flags(package,store)+['-c','model_reasoning_effort='+json.dumps(effort)]
    save();save_observation()
    with instrument(frozen.harness.Host,ledger,save_observation):
        for index,item in enumerate(plan['pending']):
            if frozen.stop_at_pair_boundary(args.stop_file,index):
                report.update(interrupted=True,stopReason='stop-file observed at continuation pair boundary',stoppedAt=time.time(),activeAttempt=None)
                save();break
            report['activeAttempt']=item['key'];save()
            try:
                row=frozen.harness.trial(root,item,configs[item['condition']],model,args.timeout)
                frozen.execution_observed(row)
            except Exception as exc:
                row={**item,'outcome':{'passed':False,'checks':0},'error':repr(exc),'eligibleForComparison':False,
                     'tokens':None,'workspace':str(root/'workspaces'/item['key']),
                     'eventsPath':str(root/'workspaces'/(item['key']+'.events.jsonl'))}
            row['cohort']='continuation-'+REVISION
            row['provenance']={'sourceReport':str(args.report.resolve()),'sourceKey':item['key'],'fixtureRevision':item['fixtureRevision']}
            report['reports'].append(row);report['activeAttempt']=None;save()
            print(json.dumps({'key':row['key'],'passed':row['outcome']['passed'],'actions':frozen.actions(row)}),flush=True)
    verify_source(source,args.source_report)
    assert frozen.digest(args.source_report)==report['sourceReportSha256'],'Retained original report changed'
    for name,expected in report['continuationSourceSha256'].items():
        assert frozen.digest(ROOT/'tests'/name)==expected,'Continuation measurement source changed'
    report.update(complete=len(report['reports'])==72,endedAt=time.time())
    ledger['instrumentationEndedAt']=time.time();save_observation();save()


if __name__=='__main__':main()
