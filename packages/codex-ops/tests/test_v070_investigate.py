import copy
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import os

import evidence_packet
import files
import investigate
import investigate_plan
import investigate_query
import workflow
import workflow_inline
import workflow_preview
from structured import analyze
from presentation_policy import Presenter
from output_budget import FrameBudget


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = self.directory.name
        self.source = Path(self.root) / 'settings.py'
        self.source.write_text('DEFAULT_VERSION = "0.6.1"\n\ndef selected_version(environment):\n'
                               '    # Explicit override wins over the default.\n'
                               '    return environment.get("CODEX_CLI_PATH", DEFAULT_VERSION)\n', encoding='utf-8')

    def tearDown(self):
        self.directory.cleanup()

    def test_native_question_finds_override_with_context_and_exact_source(self):
        result = workflow.run(self.root, 'investigate', {'question': 'CODEX_CLI_PATH 在哪里覆盖默认值？'}, 'test-chat')
        self.assertEqual(result['evidenceState'], 'collected', result)
        self.assertEqual(result['operationStatus'], 'completed')
        self.assertTrue(any('environment.get' in row['text'] for row in result['items']))
        lines = self.source.read_text().splitlines()
        for row in result['items']:
            self.assertEqual(row['text'], lines[row['location']['line'] - 1])
            self.assertTrue(row['source']['revision'])
        self.assertEqual([s['phase'] for s in result['coverage']['stages']], ['discovery'])
        self.assertEqual(result['coverage']['kernel']['workerStarts'], 1)
        self.assertEqual(self.source.read_text().splitlines(), lines)

    def test_no_anchor_never_searches_entire_repository(self):
        def forbidden(*args):
            self.fail('No unbounded search is allowed')
        result = investigate.run(self.root, {'question': '为什么它没有按期更新？'}, forbidden)
        self.assertEqual(result['evidenceState'], 'needs_anchor')
        self.assertFalse(result['coverage']['searched'])

    def test_literal_anchors_cannot_inject_regex(self):
        parsed = investigate_query.parse({'question': 'find special', 'anchors': ['a.*b', 'a.*b']})
        self.assertEqual(parsed['anchors'], ['a.*b'])
        plan = investigate_plan.build(self.root, parsed)
        pattern = plan['plans'][0]['pattern']
        self.assertEqual(pattern, r'a\.\*b')
        self.assertIsNotNone(re.fullmatch(pattern, 'a.*b'))
        self.assertIsNone(re.fullmatch(pattern, 'axxxb'))
        self.assertEqual(investigate_query.anchors('How does `nextOffset` work?'), ['nextOffset'])
        self.assertEqual(investigate_query.anchors('where update selected'), ['update', 'selected'])

    def test_invalid_options_rejected_without_running(self):
        cases = [{'question': ''}, {'question': 'x', 'paths': []}, {'question': 'x', 'focus': 'magic'},
                 {'question': 'x', 'anchors': [1]}, {'question': 'x', 'maxBytes': True},
                 {'question': 'x', 'unknown': 1}, {'question': 'x'*2001}]
        for args in cases:
            with self.subTest(args=args):
                result = workflow.run(self.root, 'investigate', args, 'test-chat')
                self.assertEqual(result['error']['code'], 'WORKFLOW_REJECTED')

    def test_native_path_escape_and_no_match_remain_honest(self):
        escaped = workflow.run(self.root, 'investigate', {'question': 'version', 'paths': ['..']}, 'test-chat')
        self.assertIn(escaped['status'], ('error', 'rejected'))
        missing = workflow.run(self.root, 'investigate', {'question': 'ABSENT_SENTINEL'}, 'test-chat')
        self.assertEqual(missing['evidenceState'], 'no_match')
        self.assertEqual(missing['items'], [])

    def test_failure_in_either_stage_preserves_original_error(self):
        failure = {'status': 'error', 'effectState': 'none', 'error': {'code': 'ACCESS_DENIED', 'message': 'denied'}}
        for observation in (failure, {'status': 'partial', 'stages': [{'result': failure}]}):
            def invoke(root, operation, args):
                return observation
            self.assertIs(investigate.run(self.root, {'question': 'DEFAULT_VERSION'}, invoke), failure)

    def test_packet_budget_keeps_exact_lines_and_resume_arguments(self):
        rows = [{'path': str(self.source), 'line': n+1, 'text': str(n)+'x'*500} for n in range(20)]
        result = {'status': 'completed', 'search': {'complete': True},
                  'context': {'items': [{'path': str(self.source), 'revision': 'revision', 'items': rows}]}}
        stages = [{'phase': 'discovery', 'args': {'path': '.', 'pattern': 'x'}, 'result': result}]
        query = {'anchors': ['x'], 'focus': 'auto', 'maxBytes': 4096}
        before = copy.deepcopy(result)
        packet = evidence_packet.build(query, stages)
        self.assertLessEqual(len(json.dumps(packet, separators=(',', ':'), ensure_ascii=False).encode()), 4096)
        self.assertEqual(packet['status'], 'partial')
        self.assertGreater(packet['coverage']['omittedEvidenceLines'], 0)
        self.assertEqual(packet['continuations'][0]['args']['pattern'], 'x')
        self.assertEqual(result, before)
        for row in packet['items']:
            self.assertIn(row['text'], [item['text'] for item in rows])

    def test_metadata_over_budget_is_explicit_failure(self):
        stage = {'phase': 'discovery', 'args': {'path': 'x'*5000}, 'result': {}}
        result = evidence_packet.build({'anchors': ['x'], 'focus': 'auto', 'maxBytes': 4096}, [stage])
        self.assertEqual(result['error']['code'], 'EVIDENCE_BUDGET')

    def test_packet_is_not_recaptured_and_internal_value_unchanged(self):
        result = workflow.run(self.root, 'investigate', {'question': 'CODEX_CLI_PATH'}, 'test-chat')
        original = copy.deepcopy(result)
        class NoCapture:
            def capture(self, *args):
                raise AssertionError('Evidence packet should be returned directly')
        wrapped = workflow_preview.capture(NoCapture(), result, 'investigate')
        self.assertIs(wrapped['value'], result)
        raw = json.dumps(wrapped)
        self.assertTrue(workflow_inline.eligible(raw, analyze(raw)))
        self.assertEqual(result, original)
        for field, value in [('coverage', []), ('items', None), ('evidenceState', 'guessed')]:
            broken = {**result, field: value}
            self.assertFalse(workflow_inline._packet(broken))

    def test_partial_source_and_invalid_lines_are_not_claimed_complete(self):
        stage = {'phase': 'discovery', 'args': {'path': '.'}, 'result': {'status': 'partial',
                 'context': {'items': [{'items': [{'text': 'bad line', 'line': '1'}, {'line': 2}]}]}}}
        packet = evidence_packet.build({'anchors': ['x'], 'focus': 'auto', 'maxBytes': 4096}, [stage])
        self.assertEqual(packet['status'], 'partial')
        self.assertEqual(packet['items'], [])

    def test_medium_packet_passthrough_still_obeys_shared_frame_budget(self):
        packet = workflow.run(self.root, 'investigate', {'question': 'CODEX_CLI_PATH'}, 'test-chat')
        packet['items'][0]['text'] = 'full evidence ' * 800
        original = copy.deepcopy(packet)
        raw = json.dumps({'kind': 'inline', 'value': packet})
        self.assertGreater(len(raw.encode()), 8192)
        self.assertLess(len(raw.encode()), 24576)
        self.assertTrue(workflow_inline.eligible(raw, analyze(raw)))
        with patch.dict(os.environ, {'CODEX_OPS_STORE': str(Path(self.root)/'cache')}):
            direct = json.loads(Presenter().render(raw))
            self.assertEqual(direct['kind'], 'workflow-view')
            self.assertTrue(direct['evidence'])
            frame = FrameBudget(Presenter(), [len(raw.encode())]*2)
            shown = json.loads(frame.render(raw))
            self.assertEqual(shown['kind'], 'workflow-view')
            self.assertLess(len(json.dumps(shown).encode()), 6000)
        self.assertEqual(packet, original)

    def test_medium_claim_requires_exact_packet_shape(self):
        value = evidence_packet.needs_anchor({})
        for row in [None, {'text': 'x'}, {'text': 'x', 'source': {}, 'location': {}},
                    {'text': 'x', 'source': {'path': 'x'}, 'location': {'line': '1'}}]:
            self.assertFalse(workflow_inline._packet({**value, 'items': [row]}))
        self.assertFalse(workflow_inline._packet_candidate({'value': None}))
        huge = {**value, 'nextAction': 'x'*25000}
        raw = json.dumps(huge)
        self.assertFalse(workflow_inline.eligible(raw, analyze(raw)))


if __name__ == '__main__':
    unittest.main()
