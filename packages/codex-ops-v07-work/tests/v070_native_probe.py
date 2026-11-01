"""Real native commands plus MCP investigation, recovery and bounded SDK polling."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sdk_workflow import SOURCE


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def presentation(outputs):
    """Inspect emitted JSON blocks, not a substring that a reference preview could contain."""
    operations, receipts, verification = [], 0, None
    for item in outputs:
        blocks = item.get('output', [])
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            value = _json(block.get('text', ''))
            if value.get('kind') == 'reference':
                receipts += 1
            value = _unpack(value)
            if value.get('kind') == 'evidence-packet':
                operations.append(value.get('operation'))
                if value.get('operation') == 'verify':
                    verification = {'exitCode': value.get('exitCode'),
                                    'hasFailureEvidence': 'VERIFY_070_SENTINEL' in json.dumps(value.get('diagnosis')),
                                    'observationsRef': value.get('observationsRef')}
    return {'directPacketOperations': operations, 'outerReferenceBlocks': receipts,
            'directEvidenceDelivered': 'investigate' in operations and 'evidence' in operations,
            'verificationPresentation': verification,
            'verificationDirectFailureVisible': bool(verification and verification['exitCode'] == 2 and verification['hasFailureEvidence'])}


def _json(text):
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def _unpack(value):
    if value.get('kind') == 'inline':
        return value['value']
    content = value.get('content', [])
    if len(content) == 1 and content[0].get('type') == 'text':
        return _unpack(_json(content[0].get('text')))
    return value.get('structuredContent') or value


def source(folder):
    # Native-created files are not readable by the user-process MCP worker on
    # this host. Preserve that failed interoperability trial separately; this
    # fixture tests native edits of an existing user-owned source file.
    folder.mkdir(parents=True, exist_ok=False)
    fixture = folder / 'settings.py'
    fixture.write_text('', encoding='utf-8')
    setup = '\n'.join([
        '[IO.File]::WriteAllText(' + quote(fixture) + ',' + quote(
            'POLICY_ALPHA = "allow"\n\ndef selected_policy():\n    return POLICY_ALPHA\n') + ')',
        "Write-Output 'FIXTURE_CREATED'",
    ])
    verify = '\n'.join([
        "Add-Content -LiteralPath 'runs.txt' -Value 'ONE_EXECUTION'",
        "1..320 | ForEach-Object { Write-Output ('INFO progress entry {0:D4} normal bounded native evidence payload' -f $_) }",
        'Start-Sleep -Seconds 12',
        "Write-Output 'settings.py:4: ERROR VERIFY_070_SENTINEL'",
        "Write-Output 'VERIFY_070_FINISHED'",
        'exit 2',
    ])
    configuration = {'root': str(folder), 'parent': str(folder.parent), 'setup': setup,
                     'verify': verify}
    return SOURCE + '\nconst config=' + json.dumps(configuration) + ';\n' + r'''
const unpack = response => {
  const value=response.structuredContent??JSON.parse(response.content[0].text);
  return value.kind==="inline"?value.value:value;
};
const canonical = value => {
  if(Array.isArray(value))return value.map(canonical);
  if(value!==null&&typeof value==="object")return Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])]));
  return value;
};
const select=suffix=>{
  const tool=ALL_TOOLS.find(item=>item.name===suffix||item.name.endsWith("__"+suffix));
  if(!tool)throw Error("MISSING_TOOL:"+suffix);
  return tool.name;
};
const workflowName=select("ops_workflow"), captureName=select("ops_capture"), filesName=select("ops_files");
const setup=await tools.exec_command({cmd:config.setup,workdir:config.parent,max_output_tokens:1000});
if(setup.exit_code!==0||!setup.output.includes("FIXTURE_CREATED"))throw Error("V070_SETUP_FAILED:"+JSON.stringify(setup));
const invoke=async(operation,args)=>{
  const response=await tools[workflowName]({root:config.root,operation,args});
  const raw=JSON.stringify(response), value=unpack(response);
  if(value.kind==="reference")throw Error("V070_USEFUL_EVIDENCE_RECAPTURED:"+operation);
  if(value.status==="error")throw Error("V070_OPERATION_FAILED:"+JSON.stringify(value));
  return {response,raw,value};
};
const investigation=await invoke("investigate",{question:"Where does POLICY_ALPHA select the policy?",paths:["settings.py"],maxBytes:4096});
if(investigation.value.kind!=="evidence-packet"||!investigation.value.items.some(row=>row.text.includes("return POLICY_ALPHA")))throw Error("V070_SOURCE_MISSING");
text(investigation.response);
if(JSON.stringify(investigation.response)!==investigation.raw)throw Error("RAW_CHANGED");
const readResponse=await tools[filesName]({root:config.root,operation:"read",args:{files:[{path:"settings.py",offset:1,limit:20}]}});
const read=unpack(readResponse);
if(!read.items?.[0]?.revision)throw Error("V070_REVISION_MISSING");
const nativeSnapshot=JSON.stringify(readResponse);
const capture=unpack(await tools[captureName]({value:{source:read,padding:"unrelated ".repeat(1000)}}));
if(capture.kind!=="reference")throw Error("V070_CAPTURE_NOT_REFERENCE");
const evidence=await invoke("evidence",{refs:[capture.ref],query:"POLICY_ALPHA",maxBytes:4096});
if(!evidence.value.items.some(row=>row.text.includes("POLICY_ALPHA")))throw Error("V070_INDEX_EVIDENCE_MISSING");
text(evidence.response);
const saved=await invoke("working_set",{action:"save",sources:[{ref:capture.ref,label:"policy",path:"settings.py",revision:read.items[0].revision}],pending:["Verify policy failure"]});
const resumed=await invoke("working_set",{action:"resume",workingSetRef:saved.value.workingSetRef,maxBytes:24576});
if(resumed.value.items[0].state!=="current"||!resumed.value.items[0].result.source.items[0].revision)throw Error("V070_RESUME_MISSING");
if(JSON.stringify(readResponse)!==nativeSnapshot)throw Error("RAW_CHANGED");
let executions=0,polls=0;
const originals=[];
const observedTools={exec_command:async args=>{
  executions++;const value=await tools.exec_command(args);originals.push([value,JSON.stringify(value)]);return value;
},write_stdin:async args=>{
  polls++;const value=await tools.write_stdin(args);originals.push([value,JSON.stringify(value)]);return value;
}};
for(const suffix of ["ops_workflow","ops_result"]){const name=select(suffix);observedTools[name]=tools[name];}
const ops=createOps(observedTools,ALL_TOOLS,config.root);
const verification=await ops.verifyRun({cmd:config.verify,yield_time_ms:1000,max_output_tokens:16000},{maxPolls:8,pollWaitMs:5000});
if(verification.state!=="completed"||verification.shell.exit_code!==2||executions!==1||polls<1)throw Error("V070_NATIVE_VERIFY_FAILED:"+JSON.stringify({verification,executions,polls}));
if(originals.some(([value,encoded])=>JSON.stringify(value)!==encoded))throw Error("RAW_CHANGED");
const fullOutput=verification.observations.map(item=>item.output).join("");
if(fullOutput.length<8192||(fullOutput.match(/INFO progress entry/g)??[]).length!==320||!fullOutput.includes("VERIFY_070_FINISHED"))throw Error("V070_TERMINAL_OUTPUT_LOST");
if(verification.evidence.kind!=="evidence-packet"||verification.evidence.operation!=="verify"||verification.evidence.exitCode!==2||!JSON.stringify(verification.evidence.diagnosis).includes("VERIFY_070_SENTINEL"))throw Error("V070_FAILURE_EVIDENCE_LOST");
if(!verification.evidence.observationsRef?.ref||verification.evidence.observationsRef.path!=="/observations")throw Error("V070_OBSERVATIONS_REF_MISSING");
text(verification.evidence);
const originalObservations=JSON.stringify(canonical(verification.observations));
let offset=0,observationPages=0;
const restoredParts=[];
while(true){
  const page=unpack(await tools[select("ops_result")]({...verification.evidence.observationsRef,view:"raw",offset,max_bytes:6000}));
  if(typeof page.text!=="string")throw Error("V070_OBSERVATION_PAGE_FAILED");
  restoredParts.push(page.text);observationPages++;
  if(page.nextOffset==null)break;
  if(page.nextOffset<=offset||observationPages>=20)throw Error("V070_OBSERVATION_PAGING_FAILED");
  offset=page.nextOffset;
}
const restoredObservations=JSON.parse(restoredParts.join(""));
if(JSON.stringify(canonical(restoredObservations))!==originalObservations)throw Error("V070_OBSERVATION_ROUNDTRIP_FAILED");
const check=await tools.exec_command({cmd:"[Console]::Write((Get-Content -LiteralPath 'runs.txt').Count)",workdir:config.root,max_output_tokens:1000});
if(check.exit_code!==0||check.output.trim()!=="1")throw Error("V070_COMMAND_REEXECUTED");
text({v070Verification:true,exitCode:verification.shell.exit_code,polls,executions,sourceCurrent:resumed.value.items[0].state,outputCharacters:fullOutput.length,observationPages,observationsExact:true});
text("V070_NATIVE_INVESTIGATED");text("V070_NATIVE_EVIDENCE");text("V070_NATIVE_RESUMED");text("V070_NATIVE_VERIFIED");text("RAW_INTACT");
'''
