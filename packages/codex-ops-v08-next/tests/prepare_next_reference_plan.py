"""Read and bind historical receipts; never launch Codex or change its configuration."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent/'codex-ops-v08-work'
SCREEN_TASKS = ('chinese_domain','late_log','holdout_code_test_config','conflicting_documents')
ARMS = {'v061':36,'v070':48}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path):
    return {'path':str(path.resolve()),'sha256':sha(path)}


def verify_files(root, expected):
    for name,value in expected.items():
        assert sha(root/name)==value, 'Historical artifact changed: '+str(root/name)


def reference_rows(report, report_binding, expected_counts):
    assert report['complete'], 'Incomplete reports cannot become frozen references'
    result = []
    for arm,count in expected_counts.items():
        rows = [row for row in report['reports'] if row['condition']==arm]
        assert len(rows)==count, (arm,len(rows),count)
        assert len({row['key'] for row in rows})==count, 'Duplicate reference key'
        assert all(row['eligibleForComparison'] for row in rows), 'Incomplete reference measurements'
        result.extend({'report':report_binding,'key':row['key'],'task':row['task'],
                       'repeat':row['repeat'],'arm':arm,'originalStrictPassed':row['outcome']['passed']}
                      for row in rows)
    return result


def candidate_schedule(original_schedule, screen=False, supplemental=False):
    rows = [dict(row) for row in original_schedule if row['condition']=='v080']
    assert len(rows)==48
    if screen:
        rows = [row for row in rows if row['task'] in SCREEN_TASKS]
        assert len(rows)==12
    if supplemental:
        rows = [row for row in rows if row['task']=='long_command_failure']
        assert len(rows)==3
    return rows


def prepare():
    full_path = OLD/'verification/v080-full-1.json'
    supplement_path = OLD/'verification/v080-terminal-supplement-1.json'
    config_path = OLD/'verification/v080-native-configs-friction-1.json'
    full, supplement, configs = read(full_path), read(supplement_path), read(config_path)
    assert len(full['reports'])==132 and len(supplement['reports'])==9
    source_binding = {}
    for arm in ARMS:
        condition = configs[arm]
        source = Path(condition['package'])
        runtime = Path(condition['executable']).parents[1]
        verify_files(source,condition['sourceSha256'])
        verify_files(runtime,condition['stagedSha256'])
        source_binding[arm] = {'originalCondition':condition,'sourceBytesStillMatch':True,
                               'runtimeBytesStillMatch':True,'historicalProfileIsNotAnExecutionHome':True}
    original_modules = full['evaluationSha256']
    verify_files(OLD/'tests',original_modules)
    candidate_quality = read(ROOT/'verification/quality/crap.json')
    verify_files(ROOT,candidate_quality['sourceSha256'])
    candidate_stage = read(ROOT/'verification/v080-runtime-next-1-stage.json')
    verify_files(Path(candidate_stage['staged']),candidate_stage['files'])
    catalogues = {arm:next(row['nativeSkillCatalogue'] for row in full['reports'] if row['condition']==arm)
                  for arm in (*ARMS,'v080')}
    plan = {
        'status':'DESIGN_ONLY_NOT_EXECUTED','paidModelCalls':0,'sandboxSetupCalls':0,
        'globalPluginMutations':False,'candidateSourceFrozen':True,'eligibleForPaidExecution':False,
        'candidateBindings':{'quality':binding(ROOT/'verification/quality/crap.json'),
                             'sourceSha256':candidate_quality['sourceSha256'],
                             'stage':binding(ROOT/'verification/v080-runtime-next-1-stage.json'),
                             'runtimeLabel':candidate_stage['label'],'runtimePath':candidate_stage['staged'],
                             'logicalVersionAloneIsInsufficient':True},
        'historicalArtifacts':{'full132':binding(full_path),'terminalSupplement9':binding(supplement_path),
                               'conditions':binding(config_path),
                               'oldQuality':binding(OLD/'verification/quality/crap.json')},
        'references':{'originalProtocol':reference_rows(full,binding(full_path),ARMS),
                      'explicitExit7Separate':reference_rows(supplement,binding(supplement_path),{'v061':3,'v070':3})},
        'baselineConditions':source_binding,
        'recordedSkillCatalogues':catalogues,
        'oldCandidateReference':{'report':binding(full_path),'condition':'v080','attempts':48,
                                 'purpose':'Describe changes from the frozen old candidate; never overwrite its failures.'},
        'candidateSchedule':{'focusedScreen':candidate_schedule(full['schedule'],screen=True),
                             'originalProtocolMain48':candidate_schedule(full['schedule']),
                             'explicitExit7Supplement3':candidate_schedule(full['schedule'],supplemental=True)},
        'protocolBinding':{'originalEvaluationSha256':original_modules,
            'supplementManifest':binding(OLD/'verification/acceptance-v080-terminal-supplement-1.json'),
            'supplementEvaluatorSha256':supplement['evaluationSha256'],
            'rules':['Original prompts, fixtures, answer types, preservation checks, LF receipts and oracles stay unchanged.',
                     'Terminal explicit-exit7 remains a separate3-attempt candidate cohort, matched only to its old supplemental references.',
                     'Every source/protocol change gets a new candidate identity, manifest and immutable result path.',
                     'Never replace a started failure or merge screening rows into main costs.']},
        'unchangedGates':{'versus061CommonSuccess':{'nativeActionReductionMinimum':0.25,'inputReductionMinimum':0.20,
                            'uncachedInputNonIncreasing':True,'strictQualityNonRegression':True},
                          'versus070':{'strictQualityNonRegression':True,'uncachedInputNonIncreasing':True,
                                       'incrementalCallAndTokenReductions':'report actual values'},
                          'quality':{'maximumCRAP':6},'releaseGatePassed':False},
        'preExecutionReviewRequired':[
            'Parent explicitly accepts historical task-matched reference design and its time/cache limitations.',
            'New production source/runtime/skills/hooks frozen and full quality/native checks pass.',
            'Parent authorizes one bounded private-authoritative-home setup/batch/official-global-restore sequence; never provision per arm.',
            'No-paid native context-equivalence receipt compares tool schemas, on-demand skill catalogues, hook text/trust/execution, effective instructions/features/model/sandbox.',
            'Match the actual recorded38-skill catalogues (37 inherited plus the arm plugin); preserve baseline inherited skills and identify any added instruction/memory/catalogue content.',
            'All observations/oracles stay outside C:/Temp fixture roots; real native cwd and audit-marker isolation verified.',
            'Exact next candidate and reference artifact hashes are bound before any real model invocation.'],
        'executionRoute':{'recommended':'one NEW private authoritative home for a bounded batch, followed by official restore of the original global home',
            'home':'LOCALAPPDATA/CodexOps/acceptance-0.8-next-1/home',
            'profiles':'All arm plugin identities live only in this NEW home. Frozen baseline sources/runtimes are referenced read-only.',
            'auth':'Existing authorized opaque local API-auth setup may be reused without printing contents. Never copy/link Windows .sandbox or .sandbox-secrets state.',
            'setup':'Official Windows setup exactly once for the shared new home, only after parent authorization; no per-arm setup.',
            'cleanup':'Close all private hosts; official setup of original global home; confirm readiness and an actual native command. Do this after failures/cancellation as well.',
            'globalEffects':'Windows sandbox account credentials rotate for the bounded batch. Original desktop native sandbox is restored before returning control.',
            'oldReviewCandidate':'Source, cache, existing review profiles, canonical0.8 runtime and live selector remain untouched.',
            'selectedCapabilityRootsProbe':'Native MCP plugin connection proven in inert no-model test; equivalent per-thread skill/hook behavior not established. Not an acceptance replacement.',
            'globalDirectMcpProbe':'Useful for native payload/protocol checks only; does not establish whole-plugin discovery/adoption equivalence.'},
        'referenceLimitations':[
            'Task/repeat-matched historical rows are not contemporaneous randomized pairs or identical random seeds.',
            'Cache warmth, elapsed time, service load and opaque provider/model changes can differ.',
            'Report total/cached/uncached input and all-attempt/common-success costs separately; do not discount tokens to hit a threshold.',
            'Retained records identify native CLI version/build path; do not invent a historical core-binary hash absent from those receipts.',
            'Changing home may change prompt/skill/instruction content; source hashes alone do not establish equivalent measurement conditions.',
            'If material native context, CLI/model or protocol differences cannot be reconciled, historical comparison is exploratory rather than a fresh-equivalent gate.',
            'Baseline automatic service is uninstrumented; compare explicit selection and report candidate observed automatic/union counts independently.'],
        'failureInterpretation':{'oldRawGateUnchanged':'FAIL','originalLegacyTerminalRows':'retain all9 original strict failures',
                                'lateLog':'retain old candidate2 strict line-field failures; no oracle or prompt relaxation',
                                'supplement':'old9/9 explicit-exit7 success remains a separate functional observation'},
        'scope':'Only design/reference preparation. No model, sandbox or global-plugin action is authorized by this file.'}
    output = ROOT/'tests/next_acceptance_plan.v2.json'
    assert not output.exists(), 'Preserve prior design; use a new explicitly versioned output'
    output.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    return plan


if __name__=='__main__':
    plan = prepare()
    print(json.dumps({'status':plan['status'],'mainReferences':len(plan['references']['originalProtocol']),
                      'supplementReferences':len(plan['references']['explicitExit7Separate']),
                      'screenAttempts':len(plan['candidateSchedule']['focusedScreen']),
                      'mainCandidateAttempts':len(plan['candidateSchedule']['originalProtocolMain48']),
                      'separateSupplementAttempts':len(plan['candidateSchedule']['explicitExit7Supplement3']),
                      'paidModelCalls':0}))
