import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import document_routing
import document_view
import delivery_metrics
import cost_events
import evidence_packet
import evidence_selection
import files
from model_tasks import docx
from output_budget import FrameBudget, fair_share
from presentation_policy import Presenter
from reducers import encode
from store import Store
from structured import analyze
import workflow_documents
import workflow_preview
import workflow_view
import workflow_inline


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {'CODEX_OPS_STORE': str(self.root / 'store'),
                                     'CODEX_OPS_MEASUREMENT_ORIGIN': 'validation'})
        env.start()
        self.addCleanup(env.stop)
        self.store = Store()
        self.addCleanup(self.store.close)

    def save(self, value):
        return self.store.capture(value, force=True)['ref']

    def raw(self, ref):
        parts, offset = [], 0
        while True:
            page = self.store.result(ref, view='raw', offset=offset, max_bytes=16000)
            parts.append(page['text'])
            if page['nextOffset'] is None:
                return ''.join(parts)
            offset = page['nextOffset']

    def packet(self):
        stages = []
        for name in ('source.py', 'test_source.py', 'config.py'):
            path = str(self.root / name)
            rows = [{'line': i + 1, 'text': f'RETRY_LIMIT_{i} = {i} # bounded exact source'} for i in range(12)]
            result = {'status': 'completed', 'search': {'complete': True, 'scanComplete': True},
                      'context': {'complete': True, 'items': [{'path': path, 'revision': 'a' * 64, 'items': rows}]}}
            stages.append({'phase': 'expansion', 'role': 'source', 'args': {'path': path, 'pattern': 'RETRY_LIMIT'},
                           'result': result})
        return evidence_packet.build({'anchors': ['RETRY_LIMIT'], 'focus': 'auto', 'maxBytes': 12288,
                                      'kernel': {'workerStarts': 1}}, stages)

    def test_machine_values_unchanged_and_full_emission_roundtrips(self):
        value = self.packet()
        original = copy.deepcopy(value)
        raw = json.dumps({'content': [{'type': 'text', 'text': json.dumps({'kind': 'inline', 'value': value}, indent=2)}]})
        shown = json.loads(Presenter().render(raw))
        self.assertEqual(shown['kind'], 'workflow-view')
        self.assertEqual(len(shown['sources']), 3)
        self.assertEqual(shown['evidence'][0]['source'], 1)
        self.assertEqual(shown['evidence'][1]['source'], 2)
        self.assertIn('RETRY_LIMIT', shown['evidence'][0]['text'])
        self.assertLess(len(encode(shown)), len(raw) * 0.6)
        self.assertEqual(self.raw(shown['ref']), raw)
        self.assertEqual(value, original)
        self.assertEqual(value['coverage']['kernel']['workerStarts'], 1)

    def test_source_selection_does_not_spend_first_budget_on_blank_lines(self):
        rows = [{'source': {'path': 'a'}, 'location': {'line': i}, 'text': text}
                for i, text in enumerate(('', 'other', 'NEEDLE = 3'))]
        rows.append({'source': {'path': 'test_a'}, 'location': {'line': 5}, 'text': 'assert NEEDLE == 3'})
        selected = evidence_selection.prioritized(rows, ['NEEDLE'])
        self.assertEqual([row['source']['path'] for row in selected[:2]], ['a', 'test_a'])
        self.assertEqual(selected[0]['text'], 'NEEDLE = 3')
        self.assertEqual(selected[-1]['text'], '')
        self.assertEqual(evidence_selection.prioritized([], []), [])

    def test_oversized_source_row_does_not_starve_later_implementation_and_test(self):
        sources = [('docs.md', 'retry scheduling documentation'),
                   ('generated.json', 'retry ' + 'large generated value ' * 2000),
                   ('backoff.py', 'def retry_delay(): return min(delay, 8000)'),
                   ('test_backoff.py', 'def test_retry_ceiling(): assert retry_delay() == 8000')]
        for first_large in (False, True):
            ordered = ([sources[1], sources[0], *sources[2:]] if first_large else sources)
            stages = [{'phase': 'discovery', 'role': 'source', 'args': {'path': path, 'pattern': 'retry'},
                       'result': {'status': 'completed', 'search': {'complete': True},
                                  'context': {'complete': True, 'items': [{'path': path, 'revision': 'fixed',
                                              'items': [{'line': 1, 'text': content}]}]}}}
                      for path, content in ordered]
            before = copy.deepcopy(stages)
            with self.subTest(first_large=first_large):
                packet = evidence_packet.build({'anchors': ['retry'], 'focus': 'auto', 'maxBytes': 4096}, stages)
                selected = {row['source']['path']: row['text'] for row in packet['items']}
                self.assertEqual(selected, {path: content for path, content in sources if path != 'generated.json'})
                self.assertEqual(packet['coverage']['omittedEvidenceLines'], 1)
                self.assertEqual(packet['status'], 'partial')
                self.assertLessEqual(len(encode(packet).encode('utf-8')), 4096)
                self.assertEqual(stages, before)
                reference = self.save(packet)
                self.assertEqual(json.loads(self.raw(reference)), packet)

    def test_auto_documents_read_docx_table_text_without_retry(self):
        docx(self.root / 'approved.docx', ['Approved warranty is 24 months.'])
        (self.root / 'prices.csv').write_text('sku,price\nA,19\n', encoding='utf-8')
        (self.root / 'draft.md').write_text('Draft warranty is 12 months.', encoding='utf-8')
        requested = {'requests': [{'operation': 'read', 'args': {'files': [
            {'path': 'approved.docx'}, {'path': 'prices.csv'}, {'path': 'draft.md'}]}}]}
        before = copy.deepcopy(requested)
        result = workflow_documents.run(str(self.root), requested, files.run, self.save)
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual([item['operation'] for item in result['items']], ['read_docx', 'read_table', 'read'])
        self.assertEqual(result['requestedCount'], 1)
        self.assertEqual(result['requestCount'], 3)
        self.assertIn('24 months', encode(result))
        self.assertIn('12 months', encode(result))
        self.assertEqual(requested, before)

    def test_partial_documents_show_success_and_failure_without_raw_lookup(self):
        (self.root / 'policy.txt').write_text('Approved policy evidence.\n' * 500, encoding='utf-8')
        result = workflow_documents.run(str(self.root), {'requests': [
            {'operation': 'read', 'args': {'files': [{'path': 'policy.txt', 'limit': 500}]}},
            {'operation': 'read_docx', 'args': {'path': 'missing.docx'}}]}, files.run, self.save)
        self.assertEqual(result['status'], 'partial')
        raw = json.dumps({'kind': 'inline', 'value': result})
        shown = json.loads(Presenter().render(raw))
        self.assertIn(shown['kind'], ('workflow-view', 'inline'))
        visible = shown.get('documents', shown.get('value', {}).get('items'))
        self.assertEqual(len(visible), 2)
        self.assertEqual(visible[0]['status'], 'completed')
        self.assertTrue(visible[1]['error']['code'])
        self.assertIn('Approved policy', encode(shown))
        preview = workflow_preview.preview(result, 'documents')
        self.assertEqual([row['label'] for row in preview['evidence'][:2]], ['document-status'] * 2)
        if shown['kind'] == 'workflow-view':
            self.assertEqual(self.raw(shown['ref']), raw)

    def test_routing_has_explicit_units_and_bounded_batch(self):
        requests, routes = document_routing.normalize([{'operation': 'read', 'args': {'files': [
            {'path': 'BOOK.PDF', 'offset': 2, 'limit': 200}]}}])
        self.assertEqual(requests[0]['args']['limit'], 32)
        self.assertEqual(routes[0]['offsetUnit'], 'page')
        self.assertEqual(routes[0]['requestedLimit'], 200)
        for entries in ([], [None], [{'path': 'x.docx', 'limit': True}], [{'path': 'x.docx', 'unknown': 1}],
                        [{'path': f'{i}.docx'} for i in range(5)]):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                document_routing.normalize([{'operation': 'read', 'args': {'files': entries}}])

    def test_raw_pages_media_and_small_complete_values_are_not_rewritten(self):
        receipt = self.store.capture('x' * 9000, force=True)
        self.assertEqual(Presenter().render(encode(receipt)), encode(receipt))
        page = encode(self.store.result(receipt['ref'], view='raw', max_bytes=8000))
        self.assertEqual(Presenter().render(page), page)
        tiny = encode(evidence_packet.needs_anchor({}))
        self.assertEqual(Presenter().render(tiny), tiny)
        media = json.dumps({'content': [{'type': 'image', 'data': 'x' * 3000}]})
        self.assertIsNone(workflow_view.render(media, analyze(media), None, self.store.capture))

    def test_frame_budget_does_not_give_large_noise_most_of_budget(self):
        self.assertEqual(fair_share([4000, 50000], 12000), 8000)
        self.assertEqual(fair_share([40000, 50000], 12000), 6000)
        raw = json.dumps({'kind': 'inline', 'value': self.packet()})
        frame = FrameBudget(Presenter(), [len(raw.encode()), 50000])
        shown = json.loads(frame.render(raw))
        self.assertTrue(shown['evidence'])
        self.assertLess(len(encode(shown).encode()), 6500)
        self.assertEqual(FrameBudget(Presenter(), []).render('small'), 'small')

    def test_views_expose_clipping_and_table_columns(self):
        result = {'columns': ['sku', 'price'], 'items': [{'cells': ['A', '19']}, {'text': 'x' * 900}]}
        found = document_view.excerpts(result)
        self.assertEqual(found['columns'], ['sku', 'price'])
        self.assertEqual(found['items'][0]['row']['cells'], ['A', '19'])
        self.assertTrue(found['items'][1]['clipped'])
        failure = document_view.failure_view({'code': 'DENIED', 'message': 'x' * 1000})
        self.assertEqual(len(failure['message']), 400)
        self.assertTrue(failure['clipped'])

    def test_single_failed_document_and_nested_file_failures_remain_visible(self):
        (self.root / 'ok.txt').write_text('Visible source evidence.', encoding='utf-8')
        result = workflow_documents.run(str(self.root), {'requests': [{'operation': 'read', 'args': {
            'files': [{'path': 'ok.txt'}, {'path': 'missing.txt'}]}}]}, files.run, self.save)
        shown = workflow_view.project(result)
        self.assertIn('Visible source', encode(shown['evidence']))
        self.assertTrue(shown['documents'][0]['failures'][0]['error']['code'])
        self.assertFalse(shown['documents'][0]['sourceComplete'])
        failed = workflow_documents.run(str(self.root), {'requests': [
            {'operation': 'read_docx', 'args': {'path': 'absent.docx'}}]}, files.run, self.save)
        raw = encode(failed)
        self.assertTrue(workflow_inline.eligible(raw, analyze(raw)))
        self.assertTrue(workflow_view.project(failed)['documents'][0]['error']['code'])

    def test_working_set_view_retains_structured_evidence_and_hides_stale_values(self):
        value = {'operation': 'working_set', 'status': 'partial', 'items': [
            {'kind': 'working-source', 'source': {'ref': 'a'}, 'state': 'current',
             'result': {'items': [{'text': 'Current policy fact.'}]}},
            {'kind': 'working-source', 'source': {'ref': 'b'}, 'state': 'current', 'result': {'limit': 17}},
            {'kind': 'working-source', 'source': {'ref': 'c'}, 'state': 'stale', 'result': 'STALE_SENTINEL'}],
            'coverage': {}, 'pending': ['confirm policy'], 'evidenceReuse': {'hit': True, 'revisionsChecked': 2}}
        shown = workflow_view.project(value)
        self.assertIn('Current policy fact.', encode(shown))
        self.assertIn('"limit":17', encode(shown))
        self.assertNotIn('STALE_SENTINEL', encode(shown))
        self.assertEqual(shown['reuse']['revisionsChecked'], 2)
        self.assertEqual(shown['pending'], ['confirm policy'])

    def test_unavailable_projection_storage_does_not_discard_original(self):
        limited = Store(self.root / 'limited', quota=1)
        self.addCleanup(limited.close)
        raw = json.dumps({'kind': 'inline', 'value': self.packet()})
        result = workflow_view.render(raw, analyze(raw), None, lambda value: limited.capture(value, force=True))
        self.assertIsNone(result)
        receipt = self.store.capture('x' * 9000, force=True)
        unknown = encode({'ref': receipt['ref'], 'view': 'invented', 'payload': 'y' * 9000})
        shown = json.loads(Presenter().render(unknown))
        self.assertNotEqual(shown['ref'], receipt['ref'])
        self.assertEqual(self.raw(shown['ref']), unknown)

    def test_only_delivered_native_analysis_counts_as_automatic_service(self):
        raw = encode({'exit_code': 7, 'output': 'routine output\n' * 700 + 'custom final failure\n'})
        shown = json.loads(Presenter().render(raw))
        self.assertEqual(shown['preview']['kind'], 'native-observation')
        self.assertEqual(shown['preview']['exit_code'], 7)
        initial = cost_events.snapshot(origin='validation')
        automatic = [row for row in initial['groups'] if row['kind'] == 'automatic']
        self.assertEqual(sum(row['count'] for row in automatic), 1)
        for invalid in ('not json', '[]', '{}', '{"preview":{}}',
                        '{"preview":{"kind":"native-observation","exit_code":true}}'):
            self.assertFalse(delivery_metrics.record_delivered(invalid))
        Presenter().render(encode({'exit_code': 0, 'output': 'small success'}))
        current = cost_events.snapshot(origin='validation')
        self.assertEqual(current['groups'], initial['groups'])
        self.assertEqual(self.raw(shown['ref']), raw)


if __name__ == '__main__':
    unittest.main()
