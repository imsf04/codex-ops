import json
import tempfile
import unittest
from unittest.mock import patch

from store import Store
from reducers import encode, preview
from presentation_policy import Presenter
import retrieval_views
import record_preview


class RetrievalExpansionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_outline_routes_nested_results_without_returning_bodies(self):
        value = {'a/b': [{'text': 'payload' * 2000}], '~log': 'hello\nworld', 'count': 2}
        ref = self.store.capture(encode(value), force=True)['ref']
        page = self.store.result(ref, view='outline', limit=2)
        self.assertEqual(page['items'][0], {'path': '/a~1b', 'type': 'list', 'size': 1})
        self.assertEqual(page['nextOffset'], 2)
        child = self.store.result(ref, view='outline', path='/a~1b')
        self.assertEqual(child['items'][0]['path'], '/a~1b/0')
        scalar = self.store.result(ref, view='outline', path='/count')
        self.assertEqual(scalar['items'][0]['type'], 'int')
        self.assertEqual(self.store.get(ref), encode(value))

    def test_outline_describes_only_the_requested_slice(self):
        value = [None] * 100000
        ref = self.store.capture(value, force=True)['ref']
        with patch.object(retrieval_views, 'describe', wraps=retrieval_views.describe) as describe:
            result = self.store.result(ref, view='outline', offset=50000, limit=3)
        self.assertEqual(describe.call_count, 3)
        self.assertEqual(result['matchedItems'], 100000)
        self.assertEqual(result['nextOffset'], 50003)
        self.assertFalse(result['complete'])
        empty = self.store.capture({}, force=True)['ref']
        self.assertEqual(self.store.result(empty, view='outline')['items'][0]['type'], 'dict')

    def test_find_returns_exact_pointer_line_and_literal_matches(self):
        value = {'a/b': ['first\nneedle here\nlast'], '~x': {'log': 'also needle'}, 'none': 42}
        ref = self.store.capture(value, force=True)['ref']
        page = self.store.result(ref, view='find', query='needle', limit=1)
        self.assertEqual(page['items'], [{'path': '/a~1b/0', 'line': 2, 'text': 'needle here'}])
        second = self.store.result(ref, view='find', query='needle', offset=page['nextOffset'])
        self.assertEqual(second['items'][0]['path'], '/~0x/log')
        self.assertTrue(second['scanComplete'])
        self.assertTrue(second['complete'])
        self.assertEqual(self.store.result(ref, view='find', query='absent')['items'], [])

    def test_limits_are_explicit_and_raw_limit_no_longer_means_characters(self):
        ref = self.store.capture('界' * 9000)['ref']
        raw = self.store.result(ref, view='raw', limit=6000, max_bytes=512)
        self.assertIn('text', raw)
        self.assertLessEqual(len(encode(raw).encode()), 512)
        for args in ({'view': 'find'}, {'view': 'find', 'query': 'a' * 201},
                     {'view': 'outline', 'fields': ['x']}, {'view': 'outline', 'limit': 201},
                     {'view': 'bad'}, {'limit': 0}, {'max_bytes': 500}):
            self.assertEqual(self.store.result(ref, **args)['status'], 'error')

    def test_find_scan_bound_does_not_claim_complete_coverage(self):
        with patch.object(retrieval_views, 'MAX_NODES', 2):
            records, complete = retrieval_views.find({'a': 'yes', 'b': 'yes'}, '', 'yes')
        self.assertEqual(len(records), 1)
        self.assertFalse(complete)
        ref = self.store.capture({'key' * 400: 'value'}, force=True)['ref']
        self.assertEqual(self.store.result(ref, view='outline', max_bytes=512)['status'], 'error')

    def test_single_string_hits_lines_and_characters_are_bounded(self):
        samples = [('needle\n' * 100000, 'needle', 'matches'),
                   ('miss\n' * 30000, 'needle', 'lines'),
                   ('x' * (retrieval_views.MAX_CHARACTERS + 1), 'needle', 'characters')]
        for text, query, reason in samples:
            with self.subTest(reason=reason):
                ref = self.store.capture(text, force=True)['ref']
                result = self.store.result(ref, view='find', query=query)
                self.assertEqual(result['scanTruncatedBy'], reason)
                self.assertFalse(result['scanComplete'])
                self.assertFalse(result['complete'])
                self.assertLessEqual(result['matchedItems'], retrieval_views.MAX_MATCHES)
                self.assertIn('Narrow', result['nextAction'])
                self.assertIn('lines', result['scanLimits'])
                self.assertLessEqual(len(encode(result).encode()), 6000)

    def test_find_unicode_line_numbers_and_partial_scan_page_end(self):
        ref = self.store.capture({'value': 'first\r\nneedle\rneedle\u2028needle'}, force=True)['ref']
        result = self.store.result(ref, view='find', query='needle')
        self.assertEqual([row['line'] for row in result['items']], [2, 3, 4])
        with patch.object(retrieval_views, 'MAX_MATCHES', 1):
            bounded = self.store.result(ref, view='find', query='needle')
        self.assertTrue(bounded['pageComplete'])
        self.assertFalse(bounded['complete'])
        self.assertIsNone(bounded['nextOffset'])
        self.assertFalse(bounded['scanComplete'])

    def test_every_view_accounts_for_long_pointer_and_escaped_envelope(self):
        for key in ('k' * 1000, '\x01' * 100, '界' * 100):
            ref = self.store.capture({key: ['needle', '\x01' * 100]}, force=True)['ref']
            for view in ('items', 'raw', 'outline', 'find'):
                with self.subTest(key=len(key), view=view):
                    result = self.store.result(ref, view=view, path='/' + key,
                                               query='needle' if view == 'find' else '', max_bytes=512)
                    self.assertLessEqual(len(encode(result).encode()), 512)
                    if result.get('status') != 'error':
                        self.assertNotEqual(result.get('nextOffset'), result['offset'])

    def test_empty_page_metadata_is_bounded_and_raw_progresses(self):
        ref = self.store.capture({'k' * 1000: []}, force=True)['ref']
        for view in ('items', 'raw', 'find'):
            result = self.store.result(ref, view=view, path='/' + 'k' * 1000,
                                       query='needle' if view == 'find' else '', max_bytes=512)
            self.assertEqual(result['status'], 'error')
            self.assertLessEqual(len(encode(result).encode()), 512)
        missing = self.store.result(ref, view='find', path='/' + 'missing' * 1000, query='needle', max_bytes=512)
        self.assertEqual(missing['status'], 'error')
        self.assertLessEqual(len(encode(missing).encode()), 512)
        text = '\x01界' * 1000
        ref = self.store.capture(text, force=True)['ref']
        parts, offset = [], 0
        while True:
            result = self.store.result(ref, view='raw', offset=offset, max_bytes=512)
            self.assertLessEqual(len(encode(result).encode()), 512)
            parts.append(result['text'])
            if result['complete']:
                break
            self.assertGreater(result['nextOffset'], offset)
            offset = result['nextOffset']
        self.assertEqual(''.join(parts), text)

    def test_discovery_pages_bypass_automatic_recapture(self):
        ref = self.store.capture({'records': ['needle' * 50] * 40}, force=True)['ref']
        for view in ('outline', 'find'):
            page = self.store.result(ref, view=view, query='needle', max_bytes=16000)
            text = encode(page)
            with patch('presentation_policy._capture', side_effect=AssertionError('recapture')):
                self.assertEqual(Presenter().render(text), text)

    def test_native_file_preview_preserves_line_locations_and_continuation(self):
        rows = [{'line': n, 'path': 'a.py', 'text': f'def function_{n}(): return {n}'} for n in range(1, 31)]
        value = {'phase': 'verify', 'status': 'partial', 'complete': False, 'pending': 1,
                 'items': [{'path': 'a.py', 'revision': 'a' * 64, 'items': rows,
                            'complete': False, 'nextOffset': 31}]}
        original = encode(value)
        shown = preview(value, 1800)
        self.assertEqual(shown['kind'], 'file-ranges')
        self.assertEqual(shown['files'][0]['recordsPath'], '/items/0/items')
        self.assertEqual(shown['files'][0]['sample'][0]['line'], 1)
        self.assertEqual(shown['files'][0]['nextOffset'], 31)
        self.assertFalse(shown['complete'])
        self.assertLessEqual(len(encode(shown).encode()), 1800)
        self.assertEqual(encode(value), original)

    def test_native_search_tables_and_fallback_have_bounded_useful_samples(self):
        for rows in ([{'line': i, 'path': f'{i}.py', 'text': 'needle'} for i in range(20)],
                     ['a.py', 'b.py'], [{'cells': ['001', 'false', '界' * 1000]}], [42, None]):
            shown = preview({'phase': 'verify', 'items': rows, 'scanComplete': False}, 1200)
            self.assertEqual(shown['kind'], 'records')
            self.assertFalse(shown['scanComplete'])
            self.assertLessEqual(len(encode(shown).encode()), 1200)
        self.assertIsNone(record_preview.preview({'phase': 'verify', 'items': [], 'error': 'x' * 9000}, 512))
        self.assertFalse(record_preview._shrink({'files': []}))
        self.assertTrue(record_preview._shrink({'files': [{'sample': []}]}))
        self.assertEqual(preview({'ordinary': 1})['kind'], 'json')


if __name__ == '__main__':
    unittest.main()
