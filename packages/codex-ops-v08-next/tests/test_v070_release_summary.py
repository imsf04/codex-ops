import unittest

from summarize_v070_release import development_summary, outer_summary


class SafeSummaryTests(unittest.TestCase):
    def test_development_totals_add_stopped_usage_once(self):
        report={'reports':[{}]*72,'excludedInvalidFixtureAttempts':[{},{}],
                'developmentConsumption':{'v061':{'inputTokens':100,'cachedInputTokens':80,'uncachedInputTokens':20,'outputTokens':5},
                                          'v070':{'inputTokens':90,'cachedInputTokens':70,'uncachedInputTokens':20,'outputTokens':4}}}
        first={'attemptStates':{'recorded_completed_attempt':9,'interrupted_or_unsettled':1},
               'groups':{'v061':{'knownUsageLowerBound':{'inputTokens':10,'cachedInputTokens':8,'outputTokens':1,'totalTokens':11}},
                         'v070':{'knownUsageLowerBound':{'inputTokens':20,'cachedInputTokens':15,'outputTokens':2,'totalTokens':22}}}}
        result=development_summary(report,first)
        self.assertEqual(result['recordedCompletedAttempts'],83)
        self.assertEqual(result['interruptedAttempts'],1)
        self.assertEqual(result['knownUsageLowerBound'],{'inputTokens':220,'cachedInputTokens':173,
            'uncachedInputTokens':47,'outputTokens':12,'totalTokens':232})

    def test_outer_subset_pairs_do_not_fill_unobserved_calls_with_zero(self):
        rows=[];trials=[]
        for repeat in (1,2):
            for arm in ('v061','v070'):
                key=f'{repeat}-{arm}';rows.append({'key':key,'task':'task','repeat':repeat,'condition':arm})
                trials.append({'key':key,'condition':arm,'passed':True,
                               'outerCalls':{'available':repeat==2,'exec':5 if arm=='v061' else 3,'wait':0}})
        result=outer_summary({'reports':rows},{'trials':trials})
        self.assertEqual(result['availability']['v061']['unavailableAttempts'],1)
        self.assertEqual(result['allObservedPairs']['pairs'],1)
        self.assertEqual(result['allObservedPairs']['totals']['v061']['exec'],5)


if __name__=='__main__':unittest.main()
