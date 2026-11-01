import copy
import json
from pathlib import Path
import tempfile
import unittest

from model_tasks import all_tasks, prepare_task, evaluate_task, solve_for_self_test, write, _answer_value
from run_v06_model_benchmark import schedule, totals, recover_unexecuted
from compare_v06_models import comparison


class ModelSuiteTests(unittest.TestCase):
    def test_twenty_distinct_fixtures_reject_unsolved_and_accept_independent_solution(self):
        specs = set()
        with tempfile.TemporaryDirectory() as temporary:
            for task in all_tasks():
                with self.subTest(task=task):
                    root = Path(temporary) / task
                    expected = prepare_task(task, root)
                    specs.add(expected['spec'])
                    self.assertFalse(evaluate_task(task, root, expected)['passed'])
                    solve_for_self_test(task, root, expected)
                    self.assertTrue(evaluate_task(task, root, expected)['passed'])
                    preserved = next(iter(expected['preserved']))
                    (root / preserved).write_bytes(b'changed protected fixture')
                    self.assertFalse(evaluate_task(task, root, expected)['passed'])
        self.assertEqual(len(specs), 20)

    def test_json_oracle_rejects_wrong_scalar_type(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'task'
            expected = prepare_task('document_lookup_stock', root)
            answer = copy.deepcopy(expected['answer'])
            answer['backordered'] = False
            write(root, 'answer.json', json.dumps(answer))
            self.assertFalse(evaluate_task('document_lookup_stock', root, expected)['passed'])

    def test_location_oracle_accepts_explicit_semantic_alias_without_relaxing_source_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'task'
            expected = prepare_task('code_location_authority', root)
            answer = {**expected['answer'], 'override': 'suspension overrides ownership', 'path': 'src\\security\\authorize.py'}
            write(root, 'answer.json', json.dumps(answer))
            self.assertTrue(evaluate_task('code_location_authority', root, expected)['passed'])
            answer['override'] = 'owner'
            write(root, 'answer.json', json.dumps(answer))
            self.assertFalse(evaluate_task('code_location_authority', root, expected)['passed'])

    def test_repair_oracle_rejects_alias_and_import_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'task'
            expected = prepare_task('repair_tests_config', root)
            source = expected['selfTestSolution'].replace('copy.deepcopy(base)', 'base.copy()').replace('copy.deepcopy(value)', 'value')
            write(root, 'config_merge.py', source)
            self.assertFalse(evaluate_task('repair_tests_config', root, expected)['passed'])
            write(root, 'config_merge.py', 'syntax error !!!')
            self.assertFalse(evaluate_task('repair_tests_config', root, expected)['passed'])

    def test_log_oracle_accepts_only_documented_equivalent_interpretations(self):
        root = Path('C:/fixture')
        self.assertEqual(_answer_value('log_diagnosis_migration', root, {'root_cause': 'schema_version_mismatch'})['root_cause'], 'SCHEMA_VERSION')
        self.assertEqual(_answer_value('log_diagnosis_trace', root, {'downstream': 'orders'})['downstream'], 'ORDER_ABORTED')
        self.assertEqual(_answer_value('log_diagnosis_trace', root, {'downstream': 'billing'})['downstream'], 'billing')
        self.assertEqual(_answer_value('log_diagnosis_migration', root, {'root_cause': 'cache miss'})['root_cause'], 'cache miss')
        compiler = _answer_value('log_diagnosis_compiler', root, {'root_cause': 'TS9999: unrelated', 'observed': 'number', 'expected': 'string'})
        self.assertEqual(compiler, {'root_cause': 'TS9999: unrelated', 'observed': 'number', 'expected': 'string'})

    def test_every_answer_field_rejects_independently_wrong_value(self):
        with tempfile.TemporaryDirectory() as temporary:
            for task in all_tasks():
                root = Path(temporary) / task
                expected = prepare_task(task, root)
                if 'answer' not in expected:
                    continue
                for key, value in expected['answer'].items():
                    answer = copy.deepcopy(expected['answer'])
                    answer[key] = not value if type(value) is bool else value + 1000 if type(value) is int else 'incorrect-unrelated-value'
                    write(root, expected.get('answerFile', 'answer.json'), json.dumps(answer))
                    self.assertFalse(evaluate_task(task, root, expected)['passed'], (task, key))

    def test_schedule_preserves_all_conditions_repeats_and_rotates_order(self):
        rows = schedule(2)
        self.assertEqual(len(rows), 120)
        self.assertEqual(len({row['key'] for row in rows}), 120)
        for task in all_tasks():
            for repeat in (1, 2):
                self.assertEqual({r['condition'] for r in rows if r['task'] == task and r['repeat'] == repeat}, {'native', 'v05', 'v06'})
        self.assertNotEqual([r['condition'] for r in rows[:3]], [r['condition'] for r in rows[3:6]])

    def test_totals_preserve_failed_trials_and_missing_usage(self):
        result = totals([{'outcome': {'passed': False}, 'wallSeconds': 5, 'tokens': None},
                         {'outcome': {'passed': True}, 'wallSeconds': 4, 'tokens': {'total': {'totalTokens': 30, 'inputTokens': 25, 'cachedInputTokens': 20}}}])
        self.assertEqual(result['completed'], 2)
        self.assertEqual(result['passed'], 1)
        self.assertEqual(result['totalTokens'], 30)
        self.assertEqual(result['wallSecondsSum'], 9)

    def test_environment_recovery_never_retries_a_paid_or_model_failed_attempt(self):
        blocked = {'key': 'not-started', 'tokens': None, 'agentMessages': [], 'error': 'Native sandbox is not ready: updateRequired'}
        paid = {**blocked, 'key': 'paid', 'tokens': {'total': {'totalTokens': 10}}}
        ordinary = {**blocked, 'key': 'failed', 'error': 'model failed'}
        result = {'reports': [blocked, paid, ordinary]}
        recover_unexecuted(result)
        self.assertEqual([r['key'] for r in result['reports']], ['paid', 'failed'])
        self.assertEqual(result['environmentAttempts'][0]['key'], 'not-started')
        self.assertEqual(result['attemptNumbers']['not-started'], 2)

    def test_comparison_keeps_failure_and_withholds_invalid_savings(self):
        row = {'task': 'example', 'repeat': 1, 'model': 'fixed-model', 'workspaceLayout': 'same',
               'eligibleForComparison': True, 'tokens': {'total': {'totalTokens': 100, 'inputTokens': 90, 'cachedInputTokens': 50}},
               'wallSeconds': 10, 'completedItemsByType': {'commandExecution': 2},
               'outcome': {'passed': True}}
        left = {**row, 'key': 'left', 'condition': 'native'}
        failed = {**row, 'key': 'failed', 'condition': 'v06', 'outcome': {'passed': False}, 'wallSeconds': 2}
        value = comparison([left, failed], 'native', 'v06')
        self.assertEqual(value['newFailures'], ['failed'])
        self.assertEqual(value['comparableSuccessfulPairs'], 0)
        self.assertIsNone(value['medianPairedReductions']['wallTimeReductionPercent'])
        invalid = {**row, 'key': 'invalid', 'condition': 'v06', 'workspaceLayout': 'changed'}
        self.assertFalse(comparison([left, invalid], 'native', 'v06')['pairs'][0]['environmentValid'])

    def test_comparison_reports_negative_gains(self):
        row = {'task': 'example', 'repeat': 1, 'model': 'fixed-model', 'workspaceLayout': 'same',
               'eligibleForComparison': True, 'tokens': {'total': {'totalTokens': 100, 'inputTokens': 90, 'cachedInputTokens': 50}},
               'wallSeconds': 10, 'completedItemsByType': {'commandExecution': 2}, 'outcome': {'passed': True}}
        left = {**row, 'key': 'left', 'condition': 'native'}
        right = {**row, 'key': 'right', 'condition': 'v06', 'wallSeconds': 20}
        value = comparison([left, right], 'native', 'v06')
        self.assertEqual(value['medianPairedReductions']['wallTimeReductionPercent'], -100)
