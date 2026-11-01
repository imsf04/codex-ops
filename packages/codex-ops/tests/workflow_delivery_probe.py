"""Real MCP, Code Mode and staged bridge delivery of self-contained evidence."""
import json
from model_tasks import prepare_task


def source(folder):
    prepare_task('document_lookup', folder)
    (folder / 'build.log').write_text('passed noise\n' * 5000 + 'ERROR DELIVERY_SENTINEL\n', encoding='utf-8')
    return 'const root=' + json.dumps(str(folder)) + ';\n' + '''
const tool=ALL_TOOLS.find(t=>t.name.endsWith("ops_workflow"));
const unpack=r=>{const v=r.structuredContent??JSON.parse(r.content[0].text);return v.kind==="inline"?v.value:v;};
const documentResponse=await tools[tool.name]({root,operation:"documents",args:{requests:[
 {operation:"read_table",args:{path:"prices.csv",limit:1000}},
 {operation:"read_docx",args:{path:"policy.docx"}}
],query:"0042"}});
const original=JSON.stringify(documentResponse);
const documents=unpack(documentResponse);
if(documents.operation!=="documents" || !documents.items[1].result ||
 !documents.items[0].evidence.columns || documents.items[0].evidence.items.length!==6)
 throw new Error("DOCUMENT_CONTENT_MISSING");
text(documentResponse);
if(JSON.stringify(documentResponse)!==original)throw new Error("RAW_CHANGED");
const diagnosisResponse=await tools[tool.name]({root,operation:"diagnose",args:{logPath:"build.log"}});
const diagnosis=unpack(diagnosisResponse);
if(diagnosis.diagnostics[0].line!==5001||!diagnosis.diagnostics[0].text.includes("DELIVERY_SENTINEL"))
 throw new Error("LOG_PATH_EVIDENCE_MISSING");
text(diagnosisResponse);
text("WORKFLOW_DELIVERY_INTACT");text("RAW_INTACT");
'''
