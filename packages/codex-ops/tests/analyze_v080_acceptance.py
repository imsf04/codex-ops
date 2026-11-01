"""Publish retained full-trial measurements without waiving release criteria."""
from collections import Counter
import hashlib
import json
from pathlib import Path

import run_v080_costs as runner
import v080_metrics as metrics

ROOT = runner.ROOT
VERIFY = ROOT/'verification'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows_for(rows, arm):
    return [row for row in rows if row['condition']==arm]


def reductions(before, after):
    return {key:metrics.reduction(before[key],after[key]) for key in
            ('nativeActions','outerCalls','inputTokens','uncachedInputTokens','outputTokens','mcpWorkerStarts')}


def all_attempt_comparison(rows, baseline):
    before = {(r['task'],r['repeat']):r for r in rows_for(rows,baseline)}
    after = {(r['task'],r['repeat']):r for r in rows_for(rows,'v080')}
    paired = sorted(before.keys() & after.keys())
    totals = [metrics.total([source[key] for key in paired]) for source in (before,after)]
    return {'baseline':baseline,'candidate':'v080','pairedAttempts':len(paired),
            'baselineTotals':totals[0],'candidateTotals':totals[1],
            'reductions':reductions(*totals),'includesStrictFailures':True}


def adoption(rows, arm):
    eligible = [r for r in rows if r['adoption']['eligibleTask']]
    selected = sum(r['adoption']['selectedEligibleWorkflow'] for r in eligible)
    operations, evidence = Counter(), Counter()
    for row in rows:
        operations.update(row['adoption']['selectedOperations'])
        evidence.update(row['adoption']['evidence'])
    instrumented = arm=='v080'
    automatic = sum(r['adoption']['automaticallyServed'] for r in eligible) if instrumented else None
    union = sum(r['adoption']['selectedEligibleWorkflow'] or r['adoption']['automaticallyServed']
                for r in eligible) if instrumented else None
    count = len(eligible)
    return {'eligibleTaskAttempts':count,'uniqueTaskFamilies':len({r['task'] for r in eligible}),
            'explicitSelectedTaskAttempts':selected,'explicitSelectionRate':selected/count,
            'automaticServedObservedTaskAttempts':automatic,
            'automaticServedObservedRate':automatic/count if automatic is not None else None,
            'unionObservedTaskAttempts':union,'unionObservedRate':union/count if union is not None else None,
            'explicitOnlyUnionLowerBound':selected/count,'selectedOperations':dict(operations),
            'structuralEvidence':dict(evidence),
            'savedPacketsExcludedFromServed':sum(r['adoption']['automaticSaves'] for r in rows) if instrumented else None,
            'runtimeLedgerRowsAvailable':sum(bool(r['runtimeLedger'].get('available')) for r in rows),
            'automaticInstrumentation':('candidate0.8 observed payload-free ledger events' if instrumented
                                         else 'unavailable; raw false values are not evidence of zero automatic service'),
            'collectionComplete':False,
            'meaning':'Observed events only. Structural evidence is distinct from oracle success; save-only events are excluded.'}


def quality(rows):
    return {arm:{'attempts':len(chosen),'passed':sum(r['outcome']['passed'] for r in chosen),
                 'failed':sum(not r['outcome']['passed'] for r in chosen)}
            for arm in ('v061','v070','v080') if (chosen:=rows_for(rows,arm))}


def regression_pairs(rows, baseline):
    before = {(r['task'],r['repeat']):r for r in rows_for(rows,baseline)}
    result = []
    for row in rows_for(rows,'v080'):
        other = before.get((row['task'],row['repeat']))
        if other and other['outcome']['passed'] and not row['outcome']['passed']:
            result.append({'baselineKey':other['key'],'candidateKey':row['key'],'outcome':row['outcome']})
    return result


def runtime_evidence(rows):
    result = {}
    for arm in ('v061','v070','v080'):
        hooks, skill_reads = Counter(), 0
        for row in rows_for(rows,arm):
            hooks.update({k:row['nativeMethodsObserved'].get(k,0) for k in ('hook/started','hook/completed')})
            for event in map(json.loads,Path(row['eventsPath']).read_text(encoding='utf-8').splitlines()):
                item = event.get('params',{}).get('item',{})
                if event.get('method')=='item/completed' and item.get('type')=='commandExecution':
                    skill_reads += int('SKILL.md' in json.dumps(item.get('command','')))
        result[arm] = {'hooks':dict(hooks),'completedNativeCommandsMentioningSkillFile':skill_reads}
    return result


def consumption(path):
    report = read(path)
    rows = report['reports']
    totals = {key:sum(r.get('tokens',{}).get('total',{}).get(key,0) for r in rows)
              for key in ('inputTokens','cachedInputTokens','outputTokens','totalTokens')}
    totals['uncachedInputTokens'] = totals['inputTokens']-totals['cachedInputTokens']
    return {'report':str(path.relative_to(ROOT)),'sha256':digest(path),'attempts':len(rows),
            'knownTokens':totals,'knownOnly':True}


def main():
    destination = VERIFY/'v080-cost-summary.json'
    assert not destination.exists(), 'Keep the previous final analysis; do not overwrite silently'
    full_path = VERIFY/'v080-full-1.json'
    supplement_path = VERIFY/'v080-terminal-supplement-1.json'
    full, supplement = read(full_path), read(supplement_path)
    assert full['complete'] and len(full['reports'])==132
    assert supplement['complete'] and len(supplement['reports'])==9
    configs = read(VERIFY/'v080-native-configs-friction-1.json')
    for config in configs.values():
        runner.verify(config)
    assert full['evaluationSha256']==runner.evaluation_hashes()
    python = read(VERIFY/'quality/crap.json')
    rust = read(VERIFY/'rust-quality/latest.json')
    for name,expected in {**python['sourceSha256'],**rust['sourceSha256']}.items():
        assert digest(ROOT/name)==expected, name
    rows = full['reports']
    assert all(r['eligibleForComparison'] for r in rows), 'Incomplete measurement requires explicit review'
    affected = read(VERIFY/'acceptance-v080-terminal-supplement-1.json')['affectedOriginalRows']
    unaffected = [r for r in rows if r['key'] not in affected]
    comparisons = {name:full['summary'][name] for name in ('versus061','versus070')}
    for value in comparisons.values():
        value['reductions'] = reductions(value['baselineTotals'],value['candidateTotals'])
    files = ['v080-pilot-1.json','v080-pilot-2.json','v080-pilot-3.json',
             'v080-friction-screen-1.json','v080-full-1.json','v080-terminal-supplement-1.json']
    usage = [consumption(VERIFY/name) for name in files]
    known = {key:sum(r['knownTokens'][key] for r in usage) for key in usage[0]['knownTokens']}
    summary = {
        'version':'0.8.0','finalCandidate':True,'costGatePassed':full['summary']['costGate']['status']=='PASS',
        'releaseGatePassed':False,'releaseDecision':'No waiver inferred; parent joint review required.',
        'costGate':full['summary']['costGate'],'sourceSha256':python['sourceSha256'],
        'rustSourceSha256':rust['sourceSha256'],
        'binarySha256':{name:value for name,value in configs['v080']['sourceSha256'].items()
                       if name.startswith('bin/') and name.endswith('.exe')},
        'conditionHashes':configs,'sourceRuntimeProfileHashesVerified':True,
        'fullReport':{'path':str(full_path.relative_to(ROOT)),'sha256':digest(full_path),'attempts':132},
        'quality':{'pythonFunctions':python['functionCount'],'pythonMaximumCRAP':python['maximum'],
                   'pythonAbove6':python['above6'],'pythonCoveragePercent':python['coveragePercent'],
                   'rustFunctions':rust['functions'],'rustMaximumCRAP':rust['maximum'],'rustAbove6':rust['above6']},
        'commonSuccessComparisons':comparisons,
        'allAttemptComparisons':{arm:all_attempt_comparison(rows,arm) for arm in ('v061','v070')},
        'allAttempts':full['summary']['allAttempts'],'rawStrictQuality':quality(rows),
        'baselineSuccessCandidateFailures':{arm:regression_pairs(rows,arm) for arm in ('v061','v070')},
        'failedRows':[{'key':r['key'],'outcome':r['outcome'],'errors':r['errors'],
                       'measurementComplete':r['eligibleForComparison']} for r in rows if not r['outcome']['passed']],
        'protocolIssue':{'prospectiveManifest':'verification/acceptance-v080-terminal-supplement-1.json',
                         'affectedOriginalRows':affected,'rawRowsUnchanged':True,
                         'unaffectedStrictQualityForInterpretationOnly':quality(unaffected),
                         'supplementReport':str(supplement_path.relative_to(ROOT)),
                         'supplementSha256':digest(supplement_path),'supplementStrictQuality':quality(supplement['reports']),
                         'meaning':'Separate functional diagnosis; no replacement or merging into full132 cost or quality gates.'},
        'failureAudits':['verification/v080-failure-audit-late-log-2.json',
                        'verification/v080-failure-audit-late-log-model-view.json'],
        'adoption':{arm:adoption(rows_for(rows,arm),arm) for arm in ('v061','v070','v080')},
        'candidateLegacyAdoption':adoption([r for r in rows_for(rows,'v080')
                                          if r['task'] in {x['task'] for x in rows_for(rows,'v061')}],'v080'),
        'runtimeEvidence':runtime_evidence(rows),'productionAdoptionRate':None,
        'productionObservation':'verification/v080-preinstall-observation.json: development chat lifetime, not daily or labelled opportunities.',
        'knownValidationConsumption':{'reports':usage,'totalKnownTokens':known,
                                      'limits':'Retains invalid/interrupted pilot consumption; known usage is not a complete billing ledger.'},
        'limits':['Controlled real-model task attempts with three repeats, not natural production adoption.',
                  'Baseline automatic-serving rates and task-level union are uninstrumented/unknown; compare explicit selection only.',
                  'Candidate automatic/union values are observed events, not an exhaustive collection guarantee.',
                  'MCP worker starts exclude native command child processes; they are not total process starts.',
                  'Model outer calls, native actions, MCP worker starts and token counts are different levels.',
                  'The retained legacy terminal failures and two candidate late-log field failures remain in strict quality.',
                  'The inherited diagnostic source-path parser is identical in all arms; primary line5001 was model-visible.',
                  'No old0.7 exception or screen result substitutes for the fresh full132 gates.']}
    destination.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'summary':str(destination),'costGatePassed':summary['costGatePassed'],
                      'releaseGatePassed':False,'rawStrictQuality':summary['rawStrictQuality'],
                      'adoption':summary['adoption'],'knownValidationTokens':known}))


if __name__=='__main__':
    main()
