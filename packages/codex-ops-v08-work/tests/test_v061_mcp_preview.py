import copy
from contextlib import closing
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from output_budget import FrameBudget
from presentation_policy import Presenter
from store import Store
from structured import analyze
import workflow_inline


def documents():
    return {'status': 'completed', 'effectState': 'none', 'operation': 'documents',
            'requestCount': 1, 'sourceCompleteness': 'per-result', 'items': [
                {'index': 0, 'operation': 'read_docx', 'status': 'completed', 'sourceComplete': True,
                 'result': {'status': 'completed', 'complete': True,
                            'items': [{'block': 1, 'text': 'Exact useful evidence. ' * 130}]}}]}


def mcp(value):
    return {'content': [{'type': 'text', 'text': json.dumps({'kind': 'inline', 'value': value})}],
            'isError': False}


class WorkflowDisplayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {'CODEX_OPS_STORE': self.directory.name})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

    def test_self_contained_mcp_reply_is_visible_without_a_second_reference(self):
        original = mcp(documents())
        before = copy.deepcopy(original)
        raw = json.dumps(original)
        self.assertGreater(len(raw.encode()), 2048)
        self.assertLess(len(raw.encode()), workflow_inline.MAX_BYTES)
        self.assertTrue(workflow_inline.eligible(raw, analyze(raw)))
        self.assertEqual(Presenter().render(raw), raw)
        self.assertEqual(original, before)
        with closing(Store()) as store:
            self.assertEqual(store.stats()['liveReferences'], 0)

    def test_direct_and_structured_workflow_displays_preserve_original_envelopes(self):
        value = documents()
        for envelope in (value, {'kind': 'inline', 'value': value},
                         {'structuredContent': {'kind': 'inline', 'value': value}}):
            raw = json.dumps(envelope)
            self.assertEqual(Presenter().render(raw), raw)

    def test_diagnostic_display_preserves_log_evidence_and_line_numbers(self):
        value = {'status': 'partial', 'effectState': 'none', 'operation': 'diagnose',
                 'diagnostics': [{'line': 93, 'text': 'ERROR ' + 'detail ' * 400}],
                 'sourceRequests': [], 'context': {}, 'omittedDiagnostics': 90}
        raw = json.dumps(mcp(value))
        self.assertTrue(workflow_inline.eligible(raw, analyze(raw)))
        self.assertEqual(Presenter().render(raw), raw)

    def test_shared_frame_budget_still_compresses_and_preserves_exact_raw_value(self):
        raw = json.dumps(mcp(documents()))
        budget = FrameBudget(Presenter(), [len(raw.encode())] * 3, target=4000)
        shown = json.loads(budget.render(raw))
        self.assertEqual(shown['kind'], 'workflow-view')
        self.assertTrue(shown['evidence'])
        self.assertLess(len(json.dumps(shown).encode()), len(raw.encode()))
        with closing(Store()) as store:
            self.assertEqual(store.get(shown['ref']), raw)

    def test_large_workflow_cannot_bypass_normal_capture(self):
        value = documents()
        value['items'][0]['result']['items'][0]['text'] *= 4
        raw = json.dumps(mcp(value))
        self.assertFalse(workflow_inline.eligible(raw, analyze(raw)))
        shown = json.loads(Presenter().render(raw))
        self.assertEqual(shown['kind'], 'reference')
        with closing(Store()) as store:
            self.assertEqual(store.get(shown['ref']), raw)

    def test_outer_errors_nested_errors_and_media_keep_the_existing_path(self):
        base = documents()
        error = mcp(base)
        error['isError'] = True
        nested = copy.deepcopy(base)
        nested['items'][0]['result']['items'].append({'status': 'error', 'error': {'code': 'DENIED'}})
        media = {'structuredContent': {'kind': 'inline', 'value': base},
                 'content': [{'type': 'image', 'data': 'pixels', 'mimeType': 'image/png'}]}
        for value in (error, mcp(nested), media):
            raw = json.dumps(value)
            self.assertFalse(workflow_inline.eligible(raw, analyze(raw)))
        shown = json.loads(Presenter().render(json.dumps(error)))
        if shown.get('kind') == 'reference':
            self.assertTrue(shown['metadata']['isError'])
        else:
            self.assertEqual(shown, error)

    def test_reference_only_and_malformed_workflows_are_not_self_contained(self):
        variants = []
        base = documents()
        ref = copy.deepcopy(base)
        ref['items'][0].pop('result')
        ref['items'][0]['resultRef'] = 'ops://' + 'a' * 48
        variants.append(ref)
        for key, replacement in [('items', []), ('items', None), ('requestCount', 2),
                                 ('operation', 'unknown'), ('status', 'error'), ('effectState', 'applied')]:
            variants.append({**base, key: replacement})
        malformed = copy.deepcopy(base)
        malformed['items'][0]['sourceComplete'] = 'yes'
        variants += [malformed, {**base, 'items': [None]}, {'operation': 'documents'}, [], 'hello']
        for value in variants:
            raw = json.dumps(value)
            self.assertFalse(workflow_inline.eligible(raw, analyze(raw)))

    def test_bounded_selected_evidence_is_usable_even_when_full_source_is_referenced(self):
        value = documents()
        item = value['items'][0]
        item.pop('result')
        item['resultRef'] = 'ops://' + 'a' * 48
        item['evidence'] = {'items': [{'pointer': '/items/250', 'row': {'cells': ['0042', '1299']}}]}
        raw = json.dumps(mcp(value))
        self.assertTrue(workflow_inline.eligible(raw, analyze(raw)))
        item['evidence'] = {'items': [{'text': 'Relevant policy quote'}]}
        raw = json.dumps(mcp(value))
        self.assertTrue(workflow_inline.eligible(raw, analyze(raw)))
        for evidence in (None, {}, {'items': None}, {'items': [None]}, {'items': [{'pointer': '/items/1'}]}):
            item['evidence'] = evidence
            raw = json.dumps(mcp(value))
            self.assertFalse(workflow_inline.eligible(raw, analyze(raw)))

    def test_invalid_diagnostic_or_transport_cannot_claim_the_threshold(self):
        base = {'status': 'completed', 'effectState': 'none', 'operation': 'diagnose',
                'diagnostics': [{'line': 1, 'text': 'ERROR'}], 'context': {}, 'sourceRequests': []}
        variants = [{**base, 'diagnostics': rows} for rows in (None, [], [None], [{'line': 0, 'text': 'x'}])]
        variants += [{**base, 'context': []}, {**base, 'sourceRequests': None}]
        for value in variants:
            raw = json.dumps(value)
            self.assertFalse(workflow_inline.eligible(raw, analyze(raw)))
        analysis = analyze(json.dumps(base))
        for raw in ('invalid JSON', '[]', '{"content":[]}', '{"content":"text"}', '{"content":[null]}'):
            self.assertFalse(workflow_inline.eligible(raw, analysis))


if __name__ == '__main__':
    unittest.main()
