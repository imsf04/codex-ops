import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import files
import query_preview
from reducers import encode
from store import Store


class QueryPreviewTests(unittest.TestCase):
    def test_real_fused_search_receipt_keeps_useful_hit_context_and_raw_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lines = ['def needle_' + str(n) + '(): return ' + str(n) if n % 10 == 0 else '# surrounding ' + 'context ' * 12 for n in range(110)]
            (root / 'module.py').write_text('\n'.join(lines), encoding='utf-8')
            value = files.run(str(root), 'search', {'pattern': 'needle_', 'path': '.', 'maxMatches': 8})
            original = copy.deepcopy(value)
            store = Store(root / 'cache')
            try:
                receipt = query_preview.capture(store, value, 'search')
                self.assertEqual(receipt['kind'], 'reference')
                self.assertEqual(receipt['preview']['kind'], 'search-context')
                self.assertIn('needle_0', encode(receipt['preview']))
                self.assertEqual(receipt['preview']['contextPath'], '/context')
                self.assertEqual(store.get(receipt['ref']), value)
                self.assertEqual(value, original)
                self.assertLessEqual(len(encode(receipt['preview']).encode()), 3500)
                self.assertEqual(query_preview.capture(store, {'small': 1}, 'search')['kind'], 'inline')
                self.assertEqual(query_preview.capture(store, 'x' * 9000, 'read')['preview']['kind'], 'text')
            finally:
                store.close()

    def test_error_context_and_bounded_fallback_remain_retrievable(self):
        value = {'status': 'partial', 'context': {'status': 'error', 'error': {'code': 'WORKFLOW_TIMEOUT'}},
                 'search': {'scanComplete': False}, 'selectedMatches': 4}
        self.assertIn('WORKFLOW_TIMEOUT', encode(query_preview.preview(value)))
        with patch.object(query_preview, '_context', return_value={'large': 'x' * 9000}):
            result = query_preview.preview(value)
            self.assertTrue(result['clipped'])
            self.assertNotIn('context', result)
        calls = []
        def bounded(_, budget):
            calls.append(budget)
            return {'large': 'x' * (9000 if len(calls) == 1 else 10)}
        with patch.object(query_preview, '_context', side_effect=bounded):
            self.assertIn('context', query_preview.preview(value))
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
