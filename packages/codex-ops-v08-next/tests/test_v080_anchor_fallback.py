"""Retained failed questions against initial sources, never model answer artifacts."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import files
import investigate
import investigate_plan
import investigate_query
import native_process

CHINESE = [
    '查找发票分摊尾差归属的实现，确定 largest_first 对金额 [20, 35, 35] 的零起始 owner index，包括并列规则。',
    '查找发票金额分摊出现尾差时的实现，确定尾差归属规则以及最大金额并列时选择的索引；给出实现文件相对路径。',
    '查找发票分摊尾差归属的实现，确定相同最大金额时的索引选择',
]
ENGLISH = [
    'Determine how production schedule handles a negative delay and a delay of 9000ms. Identify implementation, caller, regression test and configuration paths. Find exact negative_ms and large_ms integer outputs.',
    'Determine how production schedule handles a negative delay and a delay of 9000ms. Identify implementation, caller, regression test and configuration paths; find exact negative_ms and large_ms values.',
]
SOURCE = {
    'docs/发票规则.md': '# 尾差归属\n分摊产生的剩余一分钱归到金额最大的项目；金额相同归到输入最前的项目。实现见 src/allocation.py。\n',
    'docs/库存规则.md': '库存余量分配到最早入库的批次，与发票尾差无关。\n',
    'src/allocation.py': 'def remainder_owner(amounts):\n    return max(range(len(amounts)), key=lambda i: amounts[i])\n',
}
CODE = {
    'lib/transport/client.py': 'from .delay import limit_delay\ndef schedule(delay, config):\n    return limit_delay(delay, config["ceiling_ms"])\n',
    'lib/transport/delay.py': 'def limit_delay(delay_ms, ceiling_ms):\n    return min(max(delay_ms, 0), ceiling_ms)\n',
    'checks/regression/test_delay.py': 'from lib.transport.delay import limit_delay\ndef test_negative_delay():\n    assert limit_delay(-5, 4200) == 0\n',
    'settings/production.json': '{"ceiling_ms":4200}\n',
    'generated/coverage/old.txt': 'Archived implementation: delay_ms is returned unchanged.\n' * 800,
}


class AnchorFallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='codex-ops-fallback-')
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, entries):
        for name, text in entries.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        self.assertFalse((self.root / 'answer.json').exists())

    def query(self, question, **args):
        with patch('native_process.subprocess.Popen', wraps=native_process.subprocess.Popen) as starts:
            result = investigate.run(str(self.root), {'question': question, **args}, files.run)
        self.assertEqual(starts.call_count, 1)
        for row in result.get('items', []):
            lines = Path(row['source']['path']).read_text(encoding='utf-8').splitlines()
            self.assertEqual(row['text'], lines[row['location']['line'] - 1])
        return result

    def test_three_retained_chinese_questions_acquire_original_domain_evidence(self):
        self.fixture(SOURCE)
        for question in CHINESE:
            with self.subTest(question=question):
                result = self.query(question)
                self.assertEqual(result['evidenceState'], 'collected', result)
                rows = [row for row in result['items'] if row['source']['path'].endswith('发票规则.md')]
                self.assertTrue(any('输入最前' in row['text'] for row in rows), result)
                self.assertEqual(result['coverage']['kernel']['workerStarts'], 1)
                attempts = result['coverage']['stages'][0]['searchAttempts']
                self.assertGreater(attempts[-1]['matches'], 0)
                if 'largest_first' in question:
                    self.assertEqual([row['basis'] for row in attempts], ['primary', 'inferred-language'])
                    self.assertEqual(attempts[0]['matches'], 0)

    def test_two_retained_answer_label_questions_cover_code_tests_configuration(self):
        self.fixture(CODE)
        for question in ENGLISH:
            with self.subTest(question=question):
                result = self.query(question)
                self.assertEqual(result['evidenceState'], 'collected', result)
                paths = {Path(row['source']['path']).relative_to(self.root).as_posix() for row in result['items']}
                self.assertEqual(paths, set(CODE) - {'generated/coverage/old.txt'})
                stages = result['coverage']['stages']
                config = next(stage for stage in stages if stage['role'] == 'configuration')
                self.assertEqual(config['searchAttempts'][-1]['basis'], 'attested-source')
                self.assertIn('ceiling_ms', config['searchAttempts'][-1]['pattern'])
                self.assertLessEqual(result['coverage']['kernel']['internalOperations'], 12)

    def test_explicit_missing_symbol_stays_authoritative(self):
        self.fixture(SOURCE)
        result = self.query(CHINESE[0], anchors=['largest_first'])
        self.assertEqual(result['evidenceState'], 'no_match')
        self.assertEqual(result['coverage']['kernel']['internalOperations'], 1)
        self.assertNotIn('searchAttempts', result['coverage']['stages'][0])

    def test_inferred_primary_success_avoids_secondary_scan_and_preserves_file_scope(self):
        self.fixture(CODE)
        result = self.query('Where is limit_delay used with configuration and regression tests?', paths=['lib/transport/delay.py'])
        self.assertEqual(result['coverage']['kernel']['internalOperations'], 2)
        self.assertEqual(result['coverage']['kernel']['plannedStages'], 1)
        self.assertEqual(len(result['coverage']['stages'][0]['searchAttempts']), 1)
        self.assertEqual({Path(row['source']['path']).name for row in result['items']}, {'delay.py'})

    def test_query_provenance_and_bounded_multilingual_candidates(self):
        inferred = investigate_query.parse({'question': CHINESE[0]})
        self.assertEqual(inferred['anchors'], ['largest_first'])
        self.assertIn('尾差', inferred['secondaryAnchors'])
        self.assertNotIn('largest_first', inferred['secondaryAnchors'])
        explicit = investigate_query.parse({'question': CHINESE[0], 'anchors': ['largest_first']})
        self.assertEqual(explicit['anchorOrigin'], 'explicit')
        self.assertEqual(explicit['secondaryAnchors'], [])
        long = investigate_query.parse({'question': ''.join(chr(0x4e00 + index) for index in range(1900))})
        self.assertLessEqual(len(long['anchors']), 32)
        self.assertEqual(investigate_query.parse({'question': '？'})['anchors'], [])

    def test_missing_requested_roles_remain_partial_without_invented_sources(self):
        self.fixture({'source.py': 'def limit_delay(value):\n    return value\n'})
        result = self.query('Find limit_delay configuration and tests', anchors=['limit_delay'])
        self.assertEqual(result['evidenceState'], 'collected')
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['coverage']['unfilledRequestedRoles'], ['tests', 'configuration'])
        self.assertEqual({Path(row['source']['path']).name for row in result['items']}, {'source.py'})


if __name__ == '__main__':
    unittest.main()
