"""Explicit Code Mode client source, independent of account-specific tool prefixes."""

SOURCE = '''function createOps(tools, catalogue, root) {
  const discover = suffix => {
    const names = catalogue.map(t => t.name).filter(n => n === suffix || n.endsWith("__" + suffix));
    if (names.length !== 1) throw new Error("Expected exactly one " + suffix + " tool; inspect available tools");
    return names[0];
  };
  const unpack = response => {
    let value = response.structuredContent;
    const blocks = response.content ?? [];
    if (value == null) value = blocks.length === 1 && blocks[0].type === "text" ? JSON.parse(blocks[0].text) : response;
    return value?.kind === "inline" ? value.value : value;
  };
  const bytes = text => {
    let count = 0;
    for (const character of text) {
      const point = character.codePointAt(0);
      count += point < 128 ? 1 : point < 2048 ? 2 : point < 65536 ? 3 : 4;
    }
    return count;
  };
  const name = discover("ops_workflow");
  const invoke = async (operation, args = {}) => unpack(await tools[name]({root, operation, args}));
  const resolve = async (result, maxBytes = 65536) => {
    if (!result || result.kind !== "reference") return result;
    if (!Number.isInteger(maxBytes) || maxBytes < 512 || maxBytes > 1048576) throw new Error("resolve maxBytes must be 512..1048576");
    const retrieve = discover("ops_result");
    let offset = 0, size = 0;
    const parts = [];
    for (let count = 0; count < 256; count++) {
      const pageBudget = Math.min(16000, maxBytes - size);
      if (pageBudget < 512) throw new Error("Remaining resolve budget cannot fit another reference page; original reference remains available");
      const page = unpack(await tools[retrieve]({ref: result.ref, view: "raw", offset, max_bytes: pageBudget}));
      if (page.ref !== result.ref || typeof page.text !== "string") throw new Error("Reference retrieval failed: " + JSON.stringify(page));
      size += bytes(page.text);
      if (size > maxBytes) throw new Error("Reference exceeds explicit resolve byte budget; original reference remains available");
      parts.push(page.text);
      if (page.nextOffset == null) return JSON.parse(parts.join(""));
      if (!Number.isInteger(page.nextOffset) || page.nextOffset <= offset) throw new Error("Invalid reference continuation");
      offset = page.nextOffset;
    }
    throw new Error("Reference exceeds 256-page resolve limit; retrieve selected fields instead");
  };
  const runAndDiagnose = async (command, diagnosticArgs = {}) => {
    if (!command || typeof command.cmd !== "string") throw new Error("Provide explicit native exec_command arguments");
    if ("log" in diagnosticArgs || "logRef" in diagnosticArgs || "logPath" in diagnosticArgs) throw new Error("runAndDiagnose supplies its own command output");
    const shell = await tools.exec_command({workdir: root, ...command});
    if (shell.session_id != null && shell.exit_code == null) return {state: "running", shell, diagnosis: null};
    if (shell.exit_code === 0) return {state: "completed", shell, diagnosis: null};
    if (typeof shell.output !== "string" || typeof shell.exit_code !== "number") return {state: "unknown", shell, diagnosis: null};
    if (bytes(shell.output) > 262144) return {state: "completed", shell, diagnosis: null, diagnosticSkipped: "Output exceeds 256 KiB; select a bounded log slice explicitly"};
    return {state: "completed", shell, diagnosis: await invoke("diagnose", {...diagnosticArgs, log: shell.output})};
  };
  const verifyRun = async (command, options = {}) => {
    if (!command || typeof command.cmd !== "string") throw new Error("Provide explicit native exec_command arguments");
    const {maxPolls = 3, pollWaitMs = 5000, diagnosticArgs = {}} = options;
    if (Object.keys(options).some(key => !["maxPolls", "pollWaitMs", "diagnosticArgs"].includes(key))) throw new Error("Unknown verification option");
    if (!Number.isInteger(maxPolls) || maxPolls < 0 || maxPolls > 8) throw new Error("maxPolls must be 0..8");
    if (!Number.isInteger(pollWaitMs) || pollWaitMs < 1000 || pollWaitMs > 5000) throw new Error("pollWaitMs must be 1000..5000");
    if (["log", "logRef", "logPath", "results"].some(key => key in diagnosticArgs)) throw new Error("verifyRun supplies its own native observations");
    const observations = [await tools.exec_command({workdir: root, ...command})];
    let shell = observations[0];
    for (let count = 0; count < maxPolls && shell.session_id != null && shell.exit_code == null; count++) {
      shell = await tools.write_stdin({session_id: shell.session_id, chars: "", yield_time_ms: pollWaitMs});
      observations.push(shell);
    }
    const state = typeof shell.exit_code === "number" ? "completed" : shell.session_id != null ? "running" : "unknown";
    const observedBytes = observations.reduce((total, item) => total + bytes(item.output ?? ""), 0);
    if (observedBytes > 262144) return {state, shell, observations, evidence: null, diagnosticSkipped: "Observed output exceeds 256 KiB; select a bounded log slice explicitly"};
    const evidence = await invoke("verify", {...diagnosticArgs, results: observations});
    return {state, shell, observations, evidence};
  };
  return Object.freeze({
    locate: args => invoke("locate", args),
    diagnose: args => invoke("diagnose", args),
    documents: args => invoke("documents", args),
    incremental: args => invoke("incremental", args),
    resolve,
    runAndDiagnose,
    verifyRun
  });
}'''

TYPES = '''type FileRange = {path: string; offset?: number; limit?: number};
type LocateArgs = {pattern: string; path?: string; glob?: string[]; caseInsensitive?: boolean; offset?: number; maxMatches?: number; maxFiles?: number; before?: number; after?: number};
type LogInput = {log: string; logRef?: never; logPath?: never} | {logRef: string; log?: never; logPath?: never} | {logPath: string; log?: never; logRef?: never};
type DiagnoseArgs = LogInput & {maxLocations?: number; maxEvidence?: number; before?: number; after?: number};
type DocumentRequest = {operation: "read" | "read_table" | "read_docx" | "read_pdf" | "inspect"; args: Record<string, unknown>};
type Outcome = Record<string, unknown>; // Preserve status, references, coverage and per-stage errors.
type Reference = {kind: "reference"; ref: string; preview?: unknown};
type WorkflowResult = Outcome | Reference;
type ExecArgs = {cmd: string; workdir?: string; yield_time_ms?: number; max_output_tokens?: number; [key: string]: unknown};
interface OpsWorkflow {
  locate(args: LocateArgs): Promise<WorkflowResult>;
  diagnose(args: DiagnoseArgs): Promise<WorkflowResult>;
  documents(args: {requests: DocumentRequest[]; query?: string; maxEvidence?: number}): Promise<WorkflowResult>;
  incremental(args: {files: FileRange[]; baselineRef?: string}): Promise<WorkflowResult>;
  resolve(result: WorkflowResult, maxBytes?: number): Promise<Outcome>;
  runAndDiagnose(command: ExecArgs, diagnosticArgs?: Omit<DiagnoseArgs, "log" | "logRef" | "logPath">): Promise<{state: string; shell: unknown; diagnosis: WorkflowResult | null; diagnosticSkipped?: string}>;
  verifyRun(command: ExecArgs, options?: {maxPolls?: number; pollWaitMs?: number; diagnosticArgs?: Omit<DiagnoseArgs, "log" | "logRef" | "logPath">}): Promise<{state: string; shell: unknown; observations: unknown[]; evidence: WorkflowResult | null; diagnosticSkipped?: string}>;
}
declare function createOps(tools: Record<string, (args: unknown) => Promise<unknown>>, catalogue: {name: string}[], root: string): OpsWorkflow;'''


def describe():
    return {'status': 'completed', 'effectState': 'none', 'operation': 'sdk',
            'javascript': SOURCE, 'typescript': TYPES,
            'example': 'const ops = createOps(tools, ALL_TOOLS, "C:/project"); const found = await ops.locate({pattern:"TODO"}); text(found); // await ops.resolve(found, 65536) only when full evidence is needed',
            'installation': 'Execute the returned factory declaration in functions.exec, then call createOps. No native registry is modified.',
            'failureContract': 'Workflow calls unwrap inline values but retain reference receipts. Explicit resolve reads at most maxBytes decoded UTF-8 bytes (default 65536, max 1 MiB), up to 256 raw pages, and throws on incomplete retrieval. Never reruns a producer. runAndDiagnose invokes only the explicitly supplied native command; running sessions remain unchanged for native polling, completed failures get bounded evidence. Native permissions and execution errors remain native.'}
