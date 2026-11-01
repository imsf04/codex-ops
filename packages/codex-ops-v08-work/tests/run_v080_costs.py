"""Fresh native-plugin three-arm evaluation. Paid execution requires --run."""
import argparse
import base64
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cost_events
from v080_native_host import NativeHost, task_events
import v080_model_tasks as tasks
import v080_metrics as metrics

COMMON = '\nFor every native command set workdir to the absolute task directory. Use no network or downloads.\n'
ARMS = ('v061','v070','v080')


def schedule(repeats=3):
    rows = []
    for repeat in range(1,repeats+1):
        for index, task in enumerate(tasks.TASKS):
            arms = ARMS if task in tasks.LEGACY else ('v070','v080')
            shift = (repeat+index) % len(arms)
            for arm in arms[shift:]+arms[:shift]:
                rows.append({'key':f'{repeat}-{task}-{arm}','task':task,'repeat':repeat,'condition':arm})
    return rows


def acceptance():
    return {'version':'0.8.0','design':'native-profile-on-demand-v1','plannedAttempts':132,'repeats':3,
            'legacyTasks':list(tasks.LEGACY),'holdoutTasks':list(tasks.HOLDOUT),
            'opportunities':tasks.OPPORTUNITIES,'opportunityUnit':'One independently labelled task attempt',
            'baseline061Targets':{'nativeActionReduction':0.25,'inputReduction':0.20,'uncachedInputNonIncreasing':True},
            'incremental070Targets':{'qualityNonRegression':True,'uncachedInputNonIncreasing':True},
            'stretchNonBlocking':{'nativeActionReductionVersus061':0.35,'inputReductionVersus061':0.30},
            'discovery':'Actual installed private plugin profiles and native SessionStart hooks; no eager skill text or tool-forcing task prompt',
            'nativeHome':'One authoritative private CODEX_HOME for shared Windows sandbox accounts; arm-specific immutable sources/runtimes/plugin-selection flags and per-attempt stores',
            'metrics':['outerCalls','nativeActions','mcpWorkerStarts','cachedInputTokens','uncachedInputTokens',
                       'outputTokens','explicitWorkflowSelection','structuralEvidence','automaticEvidence','strictOutcome'],
            'quality':'Report all attempts and every baseline-success/candidate-failure pair; review failures separately.',
            'nativeBoundary':'workspace-write, approval never, no sandbox relaxation; operator/oracle commands excluded from task-call metrics',
            'legacyFixtureRevision':'receipt-lf1 preserves the original LF oracle; no grading relaxation',
            'retention':'No failure replacement. Resume only unstarted cases with identical sources, profiles, criteria and schedule.',
            'dailyAdoption':'Not inferred from benchmark trials; live cohorts must retain purpose/version/time attribution.',
            'pilot':{'attempts':10,'repeat':1,'tasks':['code_location','conflicting_documents','holdout_changed_resume','holdout_terminal_failure'],
                     'required':'All attempts retain tokens, raw outer calls, worker observation and native outcome; candidate all four strict outcomes pass.',
                     'review':'Every failure or protocol mismatch is reviewed before full execution. Pilot never passes release cost gates.'}}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixture_inventory(root):
    return {path.relative_to(root).as_posix():digest(path) for path in root.rglob('*') if path.is_file()}


def verify(config):
    mappings = ((config['package'],config['sourceSha256']),
                (str(Path(config['executable']).parents[1]),config['stagedSha256']),
                (config['home'],config['profileFilesSha256']))
    for base, files in mappings:
        for name, expected in files.items():
            assert digest(Path(base)/name) == expected, 'Frozen source/profile/runtime changed: '+str(Path(base)/name)
    assert config.get('nativeHooksVerified') is True
    assert config.get('workerObserverVerified') is True


def native_oracle(host, task, workspace, expected):
    clean = {k:v for k,v in expected.items() if k not in ('spec','phaseOne','phaseChange','selfTestSolution')}
    payload = base64.b64encode(json.dumps(clean).encode()).decode()
    command = [str(Path(sys.base_prefix)/'python.exe'),'-I',str(ROOT/'tests/native_v080_oracle.py'),
               '--task',task,'--root',str(workspace),'--expected',payload]
    result = host.request('command/exec', {'command':command,'cwd':str(workspace),'timeoutMs':30000}, timeout=45)
    if result['exitCode']:
        return {'passed':False,'checks':0,'evaluationBlocked':True,'error':result['stderr'][-2000:]}
    return {**json.loads(result['stdout']),'evaluationSandbox':'native workspace-write'}


def operator_change(host, workspace, changes):
    code = ('import base64,json,pathlib,sys; base=pathlib.Path(sys.argv[1]); '
            'changes=json.loads(base64.b64decode(sys.argv[2])); '
            '[(base/name).write_bytes(value.encode()) for name,value in changes.items()]')
    encoded = base64.b64encode(json.dumps(changes).encode()).decode()
    command = [str(Path(sys.base_prefix)/'python.exe'),'-I','-c',code,str(workspace),encoded]
    result = host.request('command/exec', {'command':command,'cwd':str(workspace),'timeoutMs':30000}, timeout=45)
    if result['exitCode']:
        raise RuntimeError('Native operator fixture update failed: '+result['stderr'][-1500:])


def trial(root, item, config, model, effort, timeout, workspace_root=None):
    workspace = (workspace_root or root/'workspaces')/item['key']
    expected = tasks.prepare_task(item['task'], workspace)
    workspace = workspace.resolve()
    expected_path = root/'expectations'/(item['key']+'.json')
    assert not expected_path.resolve().is_relative_to(workspace), 'Oracle metadata must stay outside the task'
    expected_path.parent.mkdir(exist_ok=True)
    expected_path.write_text(json.dumps(expected,ensure_ascii=False,indent=2),encoding='utf-8')
    before = tasks.evaluate_task(item['task'], workspace, expected)
    assert not before['passed'], 'Unsolved task passed'
    initial_files = fixture_inventory(workspace)
    store = root/'stores'/item['key']
    store.mkdir(parents=True)
    store = store.resolve()
    host = NativeHost(config,workspace,store,effort)
    start = time.time()
    errors = []
    phase = 'setup'
    try:
        host.open(workspace,model)
        if fixture_inventory(workspace)!=initial_files:
            raise ValueError('Native setup changed the searched task corpus')
        phase = 'model'
        if expected.get('phaseOne'):
            host.run_phase(expected['phaseOne']+COMMON,timeout)
            operator_change(host,workspace,expected['phaseChange'])
        host.run_phase(expected['spec']+COMMON,timeout)
    except (OSError,RuntimeError,TimeoutError,queue.Empty,ValueError) as exc:
        errors.append(type(exc).__name__+': '+str(exc))
        try:
            host.interrupt()
        except (OSError,RuntimeError,TimeoutError,queue.Empty,ValueError) as interrupted:
            errors.append('Interrupt: '+str(interrupted))
    report = host.result()
    host.phase = 'oracle'
    try:
        if phase == 'setup':
            outcome = {'passed':False,'checks':0,'evaluationBlocked':True,'error':'Native preflight failed before any model task'}
        else:
            outcome = native_oracle(host,item['task'],workspace,expected)
    except (OSError,RuntimeError,TimeoutError,queue.Empty,ValueError) as exc:
        outcome = {'passed':False,'checks':0,'evaluationBlocked':True,'error':str(exc)}
    finally:
        host.close()
    events = task_events(host.events_path)
    execution = tasks.execution_observed(events,expected)
    if not execution:
        outcome = {**outcome,'passed':False,'executionEvidenceMissing':expected['executionRequired']}
    if execution and not tasks.execution_exit_observed(events,expected):
        outcome = {**outcome,'passed':False,'nativeExecutionExitMismatch':expected['executionExit']}
    ledger = cost_events.snapshot(root=store,origin='validation')
    workers = metrics.measured_workers(store)
    eligible = bool(report.get('tokens') and report.get('outerObserved') and workers['available']
                    and report['turnStatus']=='completed' and not outcome.get('evaluationBlocked') and not errors)
    return {**item,**report,'outcome':outcome,'before':before,'errors':errors,'startedAt':start,'endedAt':time.time(),
            'wallSeconds':time.time()-start,'workspace':str(workspace),'storeRoot':str(store),
            'eventsPath':str(host.events_path),'expectedPath':str(expected_path),
            'artifactPaths':{'rpc':str(host.rpc_path),'stderr':str(host.stderr_path),'oracle':str(ROOT/'tests/native_v080_oracle.py')},
            'mcpWorkers':workers,'runtimeLedger':ledger,'requiredExecutionObserved':execution,
            'preflightFailed':phase=='setup',
            'eligibleForComparison':eligible,'adoption':metrics.adoption(events,item['task'],ledger.get('groups'))}


def evaluation_hashes():
    files = ('run_v080_costs.py','v080_native_host.py','v080_metrics.py','v080_model_tasks.py',
             'v080_observed_server.py','native_v080_oracle.py','v070_model_tasks.py','v070_fixture_continuation.py',
             'model_tasks.py','model_task_variants.py','run_model_benchmark.py')
    return {name:digest(ROOT/'tests'/name) for name in files}


def archive_evaluation(root, hashes):
    destination = root/'evaluation-sources'
    destination.mkdir(exist_ok=True)
    for name,expected in hashes.items():
        target = destination/name
        if not target.exists():
            shutil.copy2(ROOT/'tests'/name,target)
        assert digest(target)==expected, 'Archived evaluation source differs: '+name
    return str(destination)


def run_parallel(report, selected, configs, args, save):
    retained = {row['key'] for row in report['reports']}
    remaining = iter(item for item in selected if item['key'] not in retained)
    pending = {}
    exhausted = False
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        while pending or not exhausted:
            stopping = args.stop_file is not None and args.stop_file.exists()
            if stopping:
                exhausted = True
                report.update(interrupted=True,stopReason='stop-file; retained all already submitted attempts')
            while not exhausted and len(pending)<args.workers:
                item = next(remaining,None)
                if item is None:
                    exhausted = True
                    break
                future = pool.submit(trial,args.run_root,item,configs[item['condition']],args.model,args.effort,args.timeout,args.workspace_root)
                pending[future] = item
                report['activeAttempts'] = [row['key'] for row in pending.values()]
                save()
            if not pending:
                break
            done, _ = wait(pending,return_when=FIRST_COMPLETED)
            for future in done:
                item = pending.pop(future)
                try:
                    row = future.result()
                except Exception as exc:
                    row = {**item,'outcome':{'passed':False,'checks':0},'error':repr(exc),'tokens':None,
                           'eligibleForComparison':False,'eventsPath':str(args.run_root/'workspaces'/(item['key']+'.events.jsonl'))}
                report['reports'].append(row)
                if row.get('preflightFailed'):
                    exhausted = True
                    report.update(interrupted=True,stopReason='Native preflight failed; no further attempts submitted')
                report['activeAttempts'] = [value['key'] for value in pending.values()]
                save()
                print(json.dumps({'key':item['key'],'passed':row['outcome']['passed'],'nativeActions':metrics.native_actions(row)}),flush=True)


def selected_schedule(pilot=False, pilot_tasks=None, screen=None):
    selected = schedule()
    if pilot:
        selected = [r for r in selected if r['repeat']==1 and r['task'] in acceptance()['pilot']['tasks']]
    if pilot_tasks:
        selected = [r for r in selected if r['task'] in pilot_tasks]
    if screen:
        tasks = {'code_location','conflicting_documents','holdout_changed_resume'}
        selected = [r for r in selected if r['condition'] in ('v070','v080') and
                    (r['task'] in tasks or (screen=='friction20' and r['task']=='holdout_terminal_failure' and r['repeat']==1))]
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--configs',type=Path)
    parser.add_argument('--report',type=Path,default=ROOT/'verification/v080-costs.json')
    parser.add_argument('--run-root',type=Path)
    parser.add_argument('--workspace-root',type=Path,help='Ordinary traversable physical fixture root, separate from private audit/store files')
    parser.add_argument('--model',default='gpt-6.1-terra')
    parser.add_argument('--effort',default='medium')
    parser.add_argument('--timeout',type=int,default=360)
    parser.add_argument('--pilot',action='store_true')
    parser.add_argument('--screen',choices=('friction18','friction20'),help='Predeclared repeated workflow screen, never a release gate')
    parser.add_argument('--pilot-task',action='append',choices=acceptance()['pilot']['tasks'],help='Run only these predeclared pilot tasks; requires --pilot')
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--stop-file',type=Path)
    parser.add_argument('--workers',type=int,default=1,choices=(1,2,3))
    args = parser.parse_args()
    assert not args.pilot_task or args.pilot, '--pilot-task requires --pilot'
    assert not args.screen or not args.pilot, '--screen and --pilot are separate cohorts'
    plan = acceptance()
    selected = selected_schedule(args.pilot,args.pilot_task,args.screen)
    if not args.run:
        print(json.dumps({'paidCalls':0,'acceptance':plan,'schedule':selected,'screen':args.screen},indent=2))
        return
    assert args.configs and args.run_root and args.workspace_root, '--configs, private --run-root and --workspace-root are required'
    configs = json.loads(args.configs.read_text(encoding='utf-8'))
    assert set(configs) == set(ARMS)
    for config in configs.values():
        verify(config)
    assert args.resume or not args.report.exists(), 'Keep previous paid results; use a distinct report'
    args.run_root.mkdir(parents=True,exist_ok=True)
    args.workspace_root.mkdir(parents=True,exist_ok=True)
    args.workspace_root = args.workspace_root.resolve()
    assert not args.run_root.resolve().is_relative_to(args.workspace_root), 'Private audit root must not be inside fixtures'
    (args.run_root/'workspaces').mkdir(exist_ok=True)
    report = {'version':'0.8.0','acceptance':plan,'configurations':configs,'schedule':selected,'pilot':args.pilot,'screen':args.screen,
              'root':str(args.run_root),'workspaceRoot':str(args.workspace_root),'model':args.model,'effort':args.effort,'evaluationSha256':evaluation_hashes(),
              'reports':[],'startedAt':time.time(),'activeAttempt':None,'activeAttempts':[],
              'workers':args.workers,'complete':False}
    if args.resume:
        previous = json.loads(args.report.read_text(encoding='utf-8'))
        for key in ('acceptance','configurations','schedule','root','workspaceRoot','model','effort','evaluationSha256','workers'):
            assert previous[key] == report[key], 'Resume configuration changed: '+key
        assert previous.get('activeAttempt') is None and previous.get('interrupted'), 'Cannot retry a started attempt'
        assert not previous.get('activeAttempts'), 'Cannot retry submitted process attempts'
        report = previous
    report['evaluationArchive'] = archive_evaluation(args.run_root,report['evaluationSha256'])
    def save():
        report['summary'] = metrics.summarize(report['reports'],len(selected))
        if args.pilot:
            report['summary']['costGate'] = {'status':'PILOT_ONLY','releaseGatePassed':False}
        if args.screen:
            report['summary']['costGate'] = {'status':'SCREEN_ONLY','releaseGatePassed':False}
        args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    if args.workers > 1:
        run_parallel(report,selected,configs,args,save)
        retained = {row['key'] for row in report['reports']}
    else:
        retained = {row['key'] for row in report['reports']}
    for item in selected:
        if args.workers > 1:
            break
        if item['key'] in retained:
            continue
        if args.stop_file and args.stop_file.exists():
            report.update(interrupted=True,stopReason='stop-file before next attempt')
            save()
            break
        report['activeAttempt'] = item['key']
        save()
        try:
            row = trial(args.run_root,item,configs[item['condition']],args.model,args.effort,args.timeout,args.workspace_root)
        except Exception as exc:
            row = {**item,'outcome':{'passed':False,'checks':0},'error':repr(exc),'tokens':None,
                   'eligibleForComparison':False,'eventsPath':str(args.run_root/'workspaces'/(item['key']+'.events.jsonl'))}
        report['reports'].append(row)
        report['activeAttempt'] = None
        save()
        print(json.dumps({'key':item['key'],'passed':row['outcome']['passed'],'nativeActions':metrics.native_actions(row)}),flush=True)
        if row.get('preflightFailed'):
            report.update(interrupted=True,stopReason='Native preflight failed before model task')
            save()
            break
    for config in configs.values():
        verify(config)
    assert report['evaluationSha256'] == evaluation_hashes(), 'Evaluation changed during paid run'
    report.update(complete=len(report['reports'])==len(selected),endedAt=time.time())
    save()


if __name__ == '__main__':
    main()
