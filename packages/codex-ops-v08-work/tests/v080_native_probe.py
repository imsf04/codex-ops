"""Native 0.8 entry, automatic recovery and exact-observation compatibility probe."""
import json
import v070_native_probe as previous


def source(folder):
    source = previous.source(folder)
    assert source.count("'runs.txt'") == 2, 'The inherited execution counter contract changed'
    # The native PowerShell host can start at C:\ despite its recorded workdir.
    # Keep the same counter and exact-once check, with an explicit fixture path.
    counter = previous.quote((folder / 'runs.txt').as_posix())
    fresh = '[IO.File]::WriteAllText(' + previous.quote(folder / 'settings.py') + ',' + previous.quote(
        'POLICY_ALPHA = "V080_FRESH_SOURCE"\n\ndef selected_policy():\n    return POLICY_ALPHA\n') + ')'
    fresh += "\nWrite-Output 'V080_SOURCE_UPDATED'"
    return source.replace("'runs.txt'", counter) + '\nconst freshCommand=' + json.dumps(fresh) + ';\n' + r'''
const automatic=await invoke("working_set",{action:"resume"});
if(!automatic.value.items.some(item=>item.state==="current"))throw Error("V080_AUTO_RECOVERY_FAILED");
const directArgs={root:config.root,question:"Where is POLICY_ALPHA selected?",args:{paths:["settings.py"]}};
const direct=await tools[workflowName](directArgs);
const directRaw=JSON.stringify(direct),directValue=unpack(direct);
if(directValue.evidenceState!=="collected"||directValue.workingSet?.state!=="saved")throw Error("V080_DIRECT_ENTRY_FAILED:"+JSON.stringify(directValue));
const again=unpack(await tools[workflowName](directArgs));
if(!again.evidenceReuse?.hit||again.evidenceReuse.revisionsChecked!==1)throw Error("V080_REUSE_FAILED:"+JSON.stringify(again));
text(direct);
const oldRevision=directValue.items.find(item=>item.source?.revision)?.source.revision;
if(!oldRevision)throw Error("V080_OLD_REVISION_MISSING");
const changed=await tools.exec_command({cmd:freshCommand,workdir:config.root,max_output_tokens:1000});
if(changed.exit_code!==0||!changed.output.includes("V080_SOURCE_UPDATED"))throw Error("V080_SOURCE_UPDATE_FAILED:"+JSON.stringify(changed));
const refreshed=await invoke("working_set",{action:"resume"});
const stale=refreshed.value.items.find(item=>item.state==="stale"), current=stale?.currentEvidence;
if(stale?.revision!==oldRevision||stale?.source?.revision!==oldRevision)throw Error("V080_STALE_METADATA_LOST:"+JSON.stringify(refreshed.value));
if(!current?.revision||current.revision===oldRevision||current.revision!==stale.currentRevision)throw Error("V080_FRESH_REVISION_FAILED:"+JSON.stringify(refreshed.value));
if(!current.items?.some(row=>row.text.includes("V080_FRESH_SOURCE"))||JSON.stringify(refreshed.value).includes('\\"allow\\"'))throw Error("V080_FRESH_SOURCE_FAILED:"+JSON.stringify(refreshed.value));
if(JSON.stringify(refreshed.value).includes('"allow"'))throw Error("V080_STALE_TEXT_RETURNED");
text(refreshed.response);
if(JSON.stringify(refreshed.response)!==refreshed.raw)throw Error("RAW_CHANGED");
if(JSON.stringify(direct)!==directRaw)throw Error("RAW_CHANGED");
text("V080_STALE_CURRENT_RECOVERY:"+JSON.stringify({oldRevision,currentRevision:current.revision,originalIntact:true}));
text("V080_DIRECT_AND_AUTO_RECOVERY:"+JSON.stringify({automatic:true,reused:true,originalIntact:true}));
text("V080_NATIVE_OBSERVATIONS_EXACT");
'''


def presentation(outputs):
    operations, receipts, verified = [], 0, False
    observations, recovery = None, []
    for item in outputs:
        for block in item.get('output', []):
            value = previous._unpack(previous._json(block.get('text', '')))
            if value.get('v070Verification') is True:
                observations = value
            if value.get('kind') == 'reference':
                receipts += 1
            if value.get('kind') not in ('evidence-packet', 'workflow-view'):
                continue
            operations.append(value.get('operation'))
            if value.get('operation') == 'working_set':
                recovery.append(_recovery(value))
            if value.get('operation') == 'verify':
                verified = value.get('exitCode') == 2 and 'VERIFY_070_SENTINEL' in json.dumps(value)
    return {'directOperations': operations, 'outerReferenceBlocks': receipts,
            'verificationFailureVisible': verified, 'nativeObservations': observations,
            'freshRecoveryVisible': any(row['valid'] for row in recovery), 'freshRecoveryEvidence': recovery}


def _recovery(value):
    pairs = _view_pairs(value) if value.get('kind') == 'workflow-view' else _packet_pairs(value)
    valid = [row for row in pairs if row['oldRevision'] and row['newRevision']
             and row['oldRevision'] != row['newRevision'] and row['revisionMatches']
             and 'V080_FRESH_SOURCE' in row['text'] and '"allow"' not in row['text']]
    return {'valid': bool(valid) and 'allow' not in json.dumps(value), 'rows': pairs}


def _packet_pairs(value):
    result = []
    for item in value.get('items', []):
        current = item.get('currentEvidence', {})
        if item.get('state') != 'stale':
            continue
        for row in current.get('items', []):
            result.append({'oldRevision': item.get('source', {}).get('revision'),
                           'newRevision': current.get('revision'),
                           'revisionMatches': current.get('revision') == item.get('currentRevision'),
                           'line': row.get('line'), 'text': row.get('text', '')})
    return result


def _view_pairs(value):
    sources, rows = value.get('sources', []), value.get('evidence', [])
    result = []
    for stale in (row for row in rows if row.get('state') == 'stale'):
        old = sources[stale['source'] - 1]
        for row in (item for item in rows if item.get('state') == 'current-read'):
            current = sources[row['source'] - 1]
            if old.get('path') == current.get('path'):
                result.append({'oldRevision': old.get('revision'), 'newRevision': current.get('revision'),
                               'revisionMatches': current.get('revision') == stale.get('currentRevision'),
                               'line': row.get('line'), 'text': row.get('text', '')})
    return result
