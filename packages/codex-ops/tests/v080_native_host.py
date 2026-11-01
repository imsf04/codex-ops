"""Use isolated installed plugins, native hooks and on-demand discovery."""
from collections import Counter
from contextlib import contextmanager
import json
import os
from pathlib import Path
import time

from run_model_benchmark import Host

RAW = 'rawResponseItem/completed'
CAPTURE = frozenset(('item/started','item/completed','turn/completed','thread/tokenUsage/updated',RAW))


@contextmanager
def codex_home(home):
    previous = os.environ.get('CODEX_HOME')
    os.environ['CODEX_HOME'] = str(home)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('CODEX_HOME', None)
        else:
            os.environ['CODEX_HOME'] = previous


def flags(effort, config):
    values = ['features.plugins=true', 'model_reasoning_effort='+json.dumps(effort)]
    values += ['plugins.'+name+'.enabled='+json.dumps(enabled)
               for name,enabled in config.get('pluginSelection',{}).items()]
    return [item for value in values for item in ('-c', value)]


class NativeHost(Host):
    def __init__(self, config, workspace, store, effort='medium'):
        self.config = config
        self.phase = 'setup'
        self.task_items = {}
        self.outer = {}
        self.raw_observed = False
        self.task_methods = Counter()
        self.workflow_items = []
        self.phase_reports = []
        self.active_turn_id = None
        audit = (store.parent/'audit'/workspace.name).resolve()
        assert not audit.is_relative_to(workspace.resolve()), 'Audit directory must stay outside the task workspace'
        assert not store.resolve().is_relative_to(workspace.resolve()), 'Observation store must stay outside the task workspace'
        audit.mkdir(parents=True,exist_ok=True)
        self.rpc_path = audit/'native.rpc.jsonl'
        self.rpc_stream = self.rpc_path.open('w',encoding='utf-8')
        with codex_home(config['home']):
            super().__init__(config['executable'], workspace, store, flags(effort,config),artifact_prefix=str(audit)+os.sep)
        for artifact in (self.rpc_path,self.events_path,self.stderr_path):
            assert not artifact.resolve().is_relative_to(workspace.resolve())

    def receive(self, timeout):
        message = self.inbox.get(timeout=timeout)
        if self.phase != 'task' or ('method' in message and 'id' in message):
            self.rpc_stream.write(json.dumps(message,ensure_ascii=False)+'\n')
            self.rpc_stream.flush()
        if message.get('transportClosed'):
            raise RuntimeError('Native app-server closed before completion')
        method = message.get('method')
        params = message.get('params', {})
        if method in CAPTURE or str(method).startswith('hook/'):
            self.events_stream.write(json.dumps({**message,'_v080Scope':self.phase},ensure_ascii=False)+'\n')
            self.events_stream.flush()
        if method == 'thread/tokenUsage/updated':
            self.tokens = params.get('tokenUsage')
        if method == 'turn/completed':
            self.turn = params['turn']
        if self.phase == 'task':
            self._observe(method, params)
        return message

    def _observe(self, method, params):
        self.task_methods[method] += 1
        item = params.get('item', {})
        if method == 'item/completed':
            self.task_items.setdefault(item.get('id'), item)
        if method == RAW:
            self.raw_observed = True
            if item.get('type') in ('custom_tool_call','function_call'):
                self.outer.setdefault(item.get('call_id'), {'name':item.get('name'),'type':item.get('type')})

    def open(self, workspace, model=None):
        self.request('initialize', {'clientInfo':{'name':'codex-ops-v080-acceptance','version':'0.8.0'},
                                    'capabilities':{'experimentalApi':True}})
        self.send({'method':'initialized'})
        readiness = self.request('windowsSandbox/readiness', None)
        if readiness.get('status') != 'ready':
            raise RuntimeError('Native sandbox is not ready: '+json.dumps(readiness))
        status = self.request('mcpServerStatus/list', {'detail':'toolsAndAuthOnly'})
        self.catalogue = status
        servers = [s for s in status['data'] if s.get('name') == self.config['serverName']]
        if len(servers) != 1:
            raise RuntimeError('Expected exactly one configured plugin MCP server')
        server = servers[0]
        if server.get('toolsError') or len(server.get('tools',{})) != self.config['toolCount']:
            raise RuntimeError('Installed plugin tools are not ready: '+json.dumps({
                'name':server.get('name'),'count':len(server.get('tools',{})),'error':server.get('toolsError')}))
        self.candidate_tools = list(server['tools'])
        self.hooks = self.request('hooks/list', {})
        self.skills = self.request('skills/list', {'cwds':[str(workspace)]})
        params = {'cwd':str(workspace),'ephemeral':True,'sandbox':'workspace-write','approvalPolicy':'never',
                  'experimentalRawEvents':True}
        if model:
            params['model'] = model
        started = self.request('thread/start', params)
        self.thread = started['thread']['id']
        return {'threadId':self.thread,'model':started.get('model')}

    def run_phase(self, spec, timeout):
        self.phase = 'task'
        self.turn = None
        started = self.request('turn/start', {'threadId':self.thread,'input':[{'type':'text','text':spec}]})
        self.active_turn_id = started['turn']['id']
        deadline = time.monotonic()+timeout
        while self.turn is None and time.monotonic() < deadline:
            self.receive(max(0.1, deadline-time.monotonic()))
        if self.turn is None:
            raise TimeoutError('Task turn did not complete')
        self.phase_reports.append({'id':self.turn['id'],'status':self.turn['status'],'error':self.turn.get('error')})
        self.phase = 'operator'

    def interrupt(self):
        if self.active_turn_id is None or self.turn is not None:
            return
        self.request('turn/interrupt', {'threadId':self.thread,'turnId':self.active_turn_id},timeout=30)
        deadline = time.monotonic()+30
        while self.turn is None and time.monotonic() < deadline:
            self.receive(max(0.1,deadline-time.monotonic()))
        if self.turn is None:
            raise TimeoutError('Interrupted task did not reach terminal state')

    def result(self):
        items = list(self.task_items.values())
        kinds = Counter(item.get('type','unknown') for item in items)
        tools = Counter(str(item.get('server'))+'.'+str(item.get('tool'))
                        for item in items if item.get('type') == 'mcpToolCall')
        calls = Counter(row['name'] for key,row in self.outer.items() if key is not None)
        messages = [{'phase':row.get('phase'),'text':row.get('text','')[:12000]}
                    for row in items if row.get('type') == 'agentMessage']
        return {'turnStatus':self.turn['status'] if self.turn else 'incomplete','phaseReports':self.phase_reports,
                'tokens':self.tokens,'completedItemsByType':dict(kinds),'completedMcpTools':dict(tools),
                'outerCalls':dict(calls) if self.raw_observed else None,'outerObserved':self.raw_observed,
                'nativeMethodsObserved':dict(self.task_methods),'agentMessages':messages,
                'candidateTools':self.candidate_tools,'threadId':self.thread,
                'nativeSkillCatalogue':getattr(self,'skills',None)}

    def close(self):
        try:
            super().close()
        finally:
            self.rpc_stream.close()


def task_events(path):
    return [row for row in (json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines())
            if row.get('_v080Scope') == 'task']
