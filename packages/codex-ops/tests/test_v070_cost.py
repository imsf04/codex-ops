import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sqlite3
import task_cost
import task_cost_records
import task_cost_workflows
import adaptive_budget
import adaptive_budget_ledger as ledger

SID = '11111111-1111-1111-1111-111111111111'
CHAT = 'chat:' + SID


def usage(identifier='response1', session=SID, input_count=100, cached=80):
    return {'type': 'token_usage_record', 'payload': {'response_id': identifier, 'thread_id': session,
        'usage': {'input_tokens': input_count, 'cached_input_tokens': cached, 'output_tokens': 10, 'total_tokens': input_count+10}}}


def fallback(session=SID):
    return {'type': 'event_msg', '_sessionId': session, 'payload': {'type': 'token_count', 'info': {
        'total_token_usage': {'input_tokens': 1000}, 'last_token_usage': {'input_tokens': 80, 'cached_input_tokens': 60}}}}


class CostTests(unittest.TestCase):
    def test_workflow_usage_counts_failures_without_fake_adoption_rate(self):
        def item(identifier,status='completed',result=None,tool='ops_workflow'):
            return {'payload':{'type':'item_completed','item':{'type':'McpToolCall','id':identifier,
                'tool':tool,'status':status,'arguments':{'operation':'investigate'},'result':result}}}
        good=item('good',result={'structuredContent':{'kind':'inline','value':{'status':'completed'}}})
        rows=[good,good,item('bad',result={'isError':True}),item('denied','failed'),
            item('business-error',result={'content':[{'type':'text','text':'{"status":"error"}'}]}),
            item('unreadable',result={'content':[{'type':'text','text':'plain'}]}),item('unknown','unknown'),
            item('other',tool='ops_result'),{'payload':{}},item(None)]
        result=task_cost_workflows.summarize(rows)
        self.assertEqual(result['selected'],6)
        self.assertEqual(result['completed'],2)
        self.assertEqual(result['failed'],3)
        self.assertEqual(result['unknown'],1)
        self.assertEqual(result['byOperation'],{'investigate':6})
        self.assertIsNone(result['eligible']);self.assertIsNone(result['adoptionRate'])
        self.assertEqual(task_cost_workflows._result({'result':{'structuredContent':['not-object']}}),{})

    def test_authoritative_dedup_and_no_double_count(self):
        records = [usage(), usage(), fallback()]
        records += [{'type': 'event_msg', '_sessionId': SID, 'payload': {'type': 'item_completed', 'item': {
            'type': 'CommandExecution', 'id': 'native'}}}] * 2
        records += [{'type': 'response_item', '_sessionId': SID, 'payload': {'type': 'custom_tool_call',
            'call_id': 'outer', 'name': 'exec'}}] * 2
        result = task_cost.summarize(records)
        self.assertEqual(result['tokens']['input_tokens'], 100)
        self.assertEqual(result['uncachedInputTokens'], 20)
        self.assertEqual(result['nativeActionCount'], 1)
        self.assertEqual(result['outerCalls'], {'exec': 1})
        self.assertEqual(result['usageSources'], {'authoritative': 1})

    def test_fallback_is_observed_last_only(self):
        result = task_cost.summarize([fallback(), fallback(), usage(session='another')])
        self.assertEqual(result['tokens']['input_tokens'], 180)
        self.assertEqual(result['usageSources']['fallback-last-request'], 1)

    def test_excludes_plugin_descendants(self):
        meta = {'type': 'session_meta', 'payload': {'id': 'child', 'parent_thread_id': 'plugin'}}
        result = task_cost.summarize([meta, usage(session='child'), usage('business')], ['plugin'])
        self.assertEqual(result['tokens']['input_tokens'], 100)
        self.assertEqual(task_cost_records.root('child', {'child':'child'}), None)

    def test_malformed_usage_is_not_counted_as_valid(self):
        for values in [(5, 6), (-1, 0), (True, 0)]:
            with self.assertRaises(ValueError):
                task_cost.summarize([usage(input_count=values[0], cached=values[1])])
        result = task_cost.summarize([{'type':'event_msg','payload':{}}])
        self.assertFalse(result['attribution']['adaptiveEligible'])

    def test_report_only_exact_chat_and_files(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory)/('rollout-'+SID+'.jsonl')
            records = [{'type':'session_meta','payload':{'id':SID}}, usage(), fallback()]
            file.write_text('\n'.join(json.dumps(r) for r in records)+'\n')
            result = task_cost.report(CHAT, directory)
            self.assertTrue(result['available'])
            self.assertEqual(result['tokens']['input_tokens'], 100)
            self.assertFalse(task_cost.report('runtime:123', directory)['available'])
            self.assertFalse(task_cost.report('chat:22222222-2222-2222-2222-222222222222', directory)['available'])
            file.write_text('invalid\n')
            self.assertFalse(task_cost.report(CHAT, directory)['available'])
            file.write_text(json.dumps(usage())+'\n{"type":')
            self.assertEqual(task_cost.report(CHAT,directory)['tokens']['input_tokens'],100)

    def test_reader_bounds(self):
        with self.assertRaises(ValueError):task_cost_records.read([])
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'a.jsonl';file.write_text('{}\n{}\n')
            with self.assertRaises(ValueError):task_cost_records.read([file], max_records=1)
            with patch.object(Path,'stat') as stat:
                stat.return_value.st_size=64*1024*1024+1
                with self.assertRaises(ValueError):task_cost_records.read([file])


class BudgetTests(unittest.TestCase):
    def test_attributed_same_chat_proxy_only(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(ledger.budget(CHAT, root=directory)['recommendedBytes'], 12288)
            for index in range(4):ledger.record_presentation('ref'+str(index), CHAT, directory, 100)
            ledger.record_retrieval('ref0', CHAT, root=directory, now=101)
            ledger.record_retrieval('ref1', CHAT, root=directory, now=102)
            result=ledger.budget(CHAT, root=directory, now=110)
            self.assertEqual(result['recommendedBytes'], 16384)
            self.assertIn('Suspected',result['qualification'])
            self.assertEqual(ledger.budget('runtime:123',root=directory,now=110)['recommendedBytes'],12288)
            self.assertEqual(ledger.budget(CHAT,root=directory,now=401)['recommendedBytes'],12288)

    def test_no_cross_chat_or_late_or_structured_reread(self):
        other='chat:22222222-2222-2222-2222-222222222222'
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(ledger.record_presentation('ref','runtime:1',directory,100))
            for index in range(4):ledger.record_presentation('ref'+str(index),CHAT,directory,100)
            ledger.record_retrieval('ref0',other,root=directory,now=102)
            ledger.record_retrieval('ref1',CHAT,root=directory,now=132)
            self.assertFalse(ledger.record_retrieval('ref2',CHAT,'items',directory,102))
            self.assertEqual(ledger.budget(CHAT,root=directory,now=133)['immediateRereads'],0)

    def test_budget_bounds_and_weak_evidence(self):
        def event(chat=CHAT, reread=True):return {'origin':'production','chatId':chat,'attributed':True,'reason':'presentation','immediateReread':reread}
        self.assertEqual(adaptive_budget.recommend([event()]*4,24576)['recommendedBytes'],24576)
        self.assertEqual(adaptive_budget.recommend([event()]*2+[event('other')]*2)['recommendedBytes'],12288)
        self.assertEqual(adaptive_budget.recommend([event()]*2+[event(reread=False)]*3)['recommendedBytes'],12288)
        self.assertEqual(adaptive_budget.recommend([{},None])['eligibleObservations'],0)
        with self.assertRaises(ValueError):adaptive_budget.recommend([],12)

    def test_storage_failure_does_not_affect_calls(self):
        with patch('adaptive_budget_ledger.sqlite3.connect',side_effect=sqlite3.OperationalError('busy')):
            self.assertFalse(ledger.record_presentation('ref',CHAT))
            with patch('adaptive_budget_ledger.Path.exists', return_value=True):
                self.assertEqual(ledger.budget(CHAT)['recommendedBytes'],12288)


if __name__=='__main__':unittest.main()
