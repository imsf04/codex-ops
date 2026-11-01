import copy
import json
from pathlib import Path
import tempfile
import unittest

import files
from model_tasks import document_lookup
from reducers import encode
from store import Store
import workflow_document_rows as rows
import workflow_documents as documents
import workflow_preview


class DocumentDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.saved = {}
        self.calls = []

    def save(self, value):
        ref = 'ops://document-' + str(len(self.saved))
        self.saved[ref] = copy.deepcopy(value)
        return ref

    def run_results(self, results, query=''):
        requests = [{'operation': 'read_docx', 'args': {'path': f'{i}.docx'}} for i in range(len(results))]
        before = copy.deepcopy(results)
        def invoke(root, operation, args):
            self.calls.append((operation, args))
            return {'status': 'completed', 'items': [{'result': value} for value in results]}
        result = documents.run('unused-by-stub', {'requests': requests, 'query': query}, invoke, self.save)
        self.assertEqual(results, before)
        self.assertEqual(len(self.calls), 1)
        return result

    def test_small_exact_results_need_no_store_or_evidence_refetch(self):
        original = {'status': 'completed', 'complete': True, 'items': [{'text': '政策：12.5% discount'}]}
        value = self.run_results([original], 'discount')
        item = value['items'][0]
        self.assertEqual(item['result'], original)
        self.assertNotIn('resultRef', item)
        self.assertNotIn('sourceCoverage', item)
        self.assertEqual(item['evidence']['items'], [{'pointer': '/items/0/text'}])
        self.assertEqual(self.saved, {})
        self.assertEqual(value['status'], 'completed')

    def test_inline_budget_is_shared_across_four_requests_and_counts_utf8(self):
        originals = [{'status': 'completed', 'complete': True, 'items': [{'text': '甲' * 600}]} for _ in range(4)]
        value = self.run_results(originals)
        inline = [item['result'] for item in value['items'] if 'result' in item]
        referenced = [item for item in value['items'] if 'resultRef' in item]
        self.assertTrue(inline)
        self.assertTrue(referenced)
        self.assertLessEqual(sum(len(encode(item).encode()) for item in inline), documents.INLINE_BYTES)
        self.assertEqual(len(inline) + len(referenced), 4)
        self.assertTrue(all('evidence' not in item for item in value['items']))
        self.assertEqual([self.saved[item['resultRef']] for item in referenced], originals[len(inline):])

    def test_partial_and_failed_inline_results_preserve_native_cursors_and_errors(self):
        partial = {'status': 'completed', 'complete': False, 'truncated': True,
                   'nextOffset': 201, 'items': [{'text': 'unrelated'}]}
        failure = {'status': 'error', 'error': {'code': 'PERMISSION_DENIED', 'effectState': 'none'}}
        value = self.run_results([partial, failure], 'needle')
        self.assertEqual(value['status'], 'partial')
        self.assertEqual(value['items'][0]['result']['nextOffset'], 201)
        self.assertEqual(value['items'][0]['matchConclusion'], 'unknown')
        self.assertEqual(value['items'][1]['result'], failure)
        self.assertEqual(self.saved, {})

    def test_large_table_evidence_contains_complete_matching_rows_and_columns(self):
        original = {'status': 'completed', 'complete': False, 'nextOffset': 201,
                    'columns': ['code', 'price'], 'items': [
                        {'row': i + 1, 'cells': [f'{i:04}', str(100 + i)]} for i in range(200)]}
        value = self.run_results([original], '0042')
        item = value['items'][0]
        self.assertEqual(item['sourceCoverage']['nextOffset'], 201)
        self.assertFalse(item['sourceComplete'])
        self.assertEqual(item['evidence']['columns'], ['code', 'price'])
        entry = item['evidence']['items'][0]
        self.assertEqual(entry, {'pointer': '/items/42', 'row': original['items'][42]})
        self.assertEqual(self.saved[item['resultRef']], original)
        self.assertNotIn('text', entry)

    def test_large_cells_keep_bounded_text_evidence_and_exact_saved_result(self):
        original = {'status': 'completed', 'complete': True, 'columns': ['text'],
                    'items': [{'cells': ['needle' + 'x' * 9000]}]}
        item = self.run_results([original], 'needle')['items'][0]
        entry = item['evidence']['items'][0]
        self.assertEqual(len(entry['text']), 400)
        self.assertTrue(entry['clipped'])
        self.assertNotIn('row', entry)
        self.assertEqual(self.saved[item['resultRef']], original)
        self.assertEqual(rows._row({'pointer': '/other', 'text': 'needle'}, original)['text'], 'needle')
        found = {'items': []}
        self.assertIs(rows.enrich(found, {'columns': 'not-a-table'}), found)
        self.assertIs(rows.enrich(found, []), found)

    def test_real_quote_fixture_returns_all_six_matching_prices_and_policy_in_one_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document_lookup(root)
            requests = [{'operation': 'read_table', 'args': {'path': 'prices.csv', 'limit': 1000}},
                        {'operation': 'read_docx', 'args': {'path': 'policy.docx'}}]
            value = documents.run(str(root), {'requests': requests, 'query': '0042'}, files.run, self.save)
            price, policy = value['items']
            self.assertEqual(len(price['evidence']['items']), 6)
            self.assertEqual(price['evidence']['columns'][4], 'unit_price_cents')
            cells = [entry['row']['cells'] for entry in price['evidence']['items']]
            self.assertIn(['0042', 'SG', '2026-09-01', 'SGD', '1299'], cells)
            self.assertTrue(price['sourceComplete'])
            self.assertIn('1250 basis points', json.dumps(policy['result']))
            self.assertEqual(len(self.saved), 1)
            self.assertEqual(self.saved[price['resultRef']]['total'], 360)
            self.assertLess(len(encode(value).encode()), 4096)
            cache = Store(root / 'cache')
            try:
                receipt = workflow_preview.capture(cache, value, 'documents')
                self.assertEqual(receipt, {'kind': 'inline', 'value': value})
            finally:
                cache.close()

    def test_preview_supports_mixed_inline_and_referenced_results(self):
        original = {'status': 'completed', 'complete': True, 'columns': ['name'],
                    'items': [{'cells': ['needle']}] * 500}
        value = self.run_results([original, {'status': 'completed', 'items': [{'text': 'policy'}]}], 'needle')
        preview = workflow_preview.preview(value, 'documents')
        self.assertIn('resultRef', preview['evidence'][0]['value'])
        self.assertEqual(preview['evidence'][0]['value']['columns'], ['name'])

    def test_non_table_reference_preview_retains_pointer_and_bounded_text(self):
        original = {'status': 'completed', 'complete': True, 'items': [{'text': 'needle' + 'x' * 9000}]}
        value = self.run_results([original], 'needle')
        preview = workflow_preview.preview(value, 'documents')
        entry = preview['evidence'][0]['value']
        self.assertEqual(entry['pointer'], '/items/0/text')
        self.assertEqual(len(entry['text']), 400)
        self.assertEqual(self.saved[entry['resultRef']], original)


if __name__ == '__main__':
    unittest.main()
