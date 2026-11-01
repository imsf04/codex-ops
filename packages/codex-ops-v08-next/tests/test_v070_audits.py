import json
from pathlib import Path
import tempfile
import unittest

from audit_stopped_v070 import audit as stopped_audit
from audit_v070_tool_chains import one_trial, rollout_calls, native_raw_calls


class AuditTests(unittest.TestCase):
    def test_cumulative_updates_count_once_and_unstarted_remains_unstarted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'workspaces').mkdir()
            events=root/'workspaces'/'one.events.jsonl'
            events.write_text('\n'.join(json.dumps({'method':'thread/tokenUsage/updated',
                'params':{'tokenUsage':{'total':{'inputTokens':n}}}}) for n in (100,250)))
            report={'root':str(root),'activeAttempt':'one','reports':[],
                    'schedule':[{'key':'one','condition':'v070'},{'key':'two','condition':'v061'}]}
            path=root/'report.json';path.write_text(json.dumps(report))
            audit=stopped_audit(path)
            self.assertEqual(audit['groups']['v070']['knownUsageLowerBound']['inputTokens'],250)
            self.assertEqual(audit['attemptStates'],{'interrupted_or_unsettled':1,'unstarted':1})
            self.assertFalse(audit['attempts'][0]['usageComplete'])

    def test_missing_rollout_is_unavailable_and_call_ids_deduplicate(self):
        self.assertFalse(rollout_calls([],{'thread'})['available'])
        self.assertIsNone(rollout_calls([],{'thread'})['exec'])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'rollout-thread.jsonl'
            call={'payload':{'type':'custom_tool_call','call_id':'same','name':'exec'}}
            path.write_text(json.dumps(call)+'\n'+json.dumps(call)+'\n')
            self.assertEqual(rollout_calls([path],{'thread'})['exec'],1)

    def test_raw_retrieval_after_native_reference_is_still_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'events.jsonl';ref='ops://'+'a'*48
            items=[{'type':'mcpToolCall','id':'origin','tool':'ops_workflow','arguments':{'operation':'locate'},
                    'result':{'kind':'reference','ref':ref}},
                   {'type':'mcpToolCall','id':'retrieve','tool':'ops_result','arguments':{'ref':ref,'view':'raw','offset':50}}]
            path.write_text('\n'.join(json.dumps({'method':'item/completed','params':{'threadId':'thread','item':i}}) for i in items))
            row={'key':'trial','task':'task','condition':'v070','outcome':{'passed':True},'eventsPath':str(path)}
            result=one_trial(row,[],{})
            self.assertEqual(result['workflowByOperation'],{'locate':1})
            case=result['retrievalCases'][0]
            self.assertEqual(case['annotation']['label'],'unknown')
            self.assertFalse(case['modelVisibleOriginProven'])
            self.assertEqual(len(case['observedNativeReferenceOrigins']),1)
            with self.assertRaises(AssertionError):
                one_trial(row,[],{'trial/retrieve':{'label':'display_missing_evidence','evidence':'native reference alone'}})

    def test_native_raw_calls_take_exact_call_scope_and_exclude_later_oracle(self):
        events=[(1,{'method':'rawResponseItem/completed','params':{'threadId':'t','turnId':'main',
                 'item':{'type':'custom_tool_call','name':'exec','call_id':'call'}}}),
                (2,{'method':'turn/completed','params':{'turn':{'id':'main'}}}),
                (3,{'method':'rawResponseItem/completed','params':{'threadId':'t','turnId':'oracle',
                 'item':{'type':'custom_tool_call','name':'exec','call_id':'oracle'}}})]
        counts=native_raw_calls(events)
        self.assertEqual(counts['exec'],1)
        self.assertEqual(counts['excludedAfterMainTurn'],1)
        self.assertIsNone(native_raw_calls([]))


if __name__=='__main__':unittest.main()
