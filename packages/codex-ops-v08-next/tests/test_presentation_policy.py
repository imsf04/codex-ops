import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from presentation_policy import Presenter
from progress import Progress
from store import Store
from structured import analyze


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'CODEX_OPS_STORE': self.temp.name})
        self.env.start()
        self.events = []
        self.presenter = Presenter(observer=lambda *args: self.events.append(args))

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def original(self, receipt):
        store = Store()
        try:
            return store.get(receipt['ref'])
        finally:
            store.close()

    def test_small_structured_results_have_usable_previews_and_exact_raw_values(self):
        value = [{'id': i, 'detail': 'detail ' * 22} for i in range(20)]
        raw = json.dumps(value)
        self.assertLess(len(raw), 8192)
        shown = json.loads(self.presenter.render(raw))
        self.assertEqual(shown['preview']['kind'], 'json')
        self.assertEqual(self.original(shown), raw)
        self.assertEqual(len(value), 20)
        self.assertEqual(self.events[-1][1], 'compacted')

    def test_repeated_progress_retains_reference_and_terminal_results(self):
        value = {'session_id': 17, 'exit_code': None, 'output': 'waiting ' * 90, 'chunk_id': 'first'}
        first = json.dumps(value)
        self.assertEqual(self.presenter.render(first), first)
        value['chunk_id'] = 'second'
        value['wall_time_seconds'] = 3
        raw = json.dumps(value)
        shown = json.loads(self.presenter.render(raw))
        self.assertEqual((shown['session_id'], shown['status'], shown['unchangedPolls']), (17, 'running', 1))
        self.assertEqual(self.original(shown), raw)
        self.assertEqual(self.events[-1][1], 'progress_unchanged')
        value['phase'] = 'changed'
        changed = json.dumps(value)
        self.assertEqual(self.presenter.render(changed), changed)
        value['exit_code'] = 7
        final = json.dumps(value)
        self.assertEqual(self.presenter.render(final), final)
        value['exit_code'] = None
        reset = json.dumps(value)
        self.assertEqual(self.presenter.render(reset), reset)

    def test_explicit_raw_pages_and_existing_receipts_are_not_recaptured(self):
        ref = 'ops://' + 'a' * 48
        for value, reason in [({'ref': ref, 'view': 'raw', 'text': 'x' * 9000, 'nextOffset': None, 'complete': True}, 'explicit_retrieval'),
                              ({'ref': ref, 'view': 'items', 'items': ['x' * 9000], 'nextOffset': None, 'complete': True}, 'explicit_retrieval'),
                              ({'kind': 'reference', 'ref': ref, 'preview': 'x' * 9000}, 'already_compact')]:
            raw = json.dumps(value)
            self.assertEqual(self.presenter.render(raw), raw)
            self.assertEqual(self.events[-1][1], reason)
        for value in ({'ref': ref, 'view': []}, {'ref': 'invalid', 'view': 'raw'}, {'ref': ref, 'view': 'raw', 'text': 'x'}):
            raw = json.dumps(value)
            self.assertEqual(self.presenter.render(raw), raw)
        too_large = json.dumps({'ref': ref, 'view': 'raw', 'text': 'x' * 70000, 'nextOffset': None, 'complete': True})
        self.assertNotEqual(self.presenter.render(too_large), too_large)

    def test_source_failure_status_and_diagnostics_are_visible(self):
        raw = json.dumps({'exit_code': 7, 'status': 'failed', 'output': 'progress\n' * 2500 + 'ERROR: original failure\n'})
        shown = json.loads(self.presenter.render(raw))
        self.assertEqual(shown['metadata']['exit_code'], 7)
        self.assertIn('original failure', json.dumps(shown['preview']))
        self.assertEqual(self.original(shown), raw)

    def test_storage_and_measurement_errors_never_change_the_source_value(self):
        raw = 'x' * 20000
        with patch('presentation_policy.Store', side_effect=OSError('unavailable')):
            self.assertEqual(self.presenter.render(raw), raw)
            self.assertEqual(self.events[-1][1], 'storage_unavailable')
        with patch('presentation_policy.Store') as factory:
            factory.return_value.capture.return_value = {'kind': 'error'}
            self.assertEqual(self.presenter.render(raw), raw)
            self.assertEqual(self.events[-1][1], 'storage_limit')
        broken = Presenter(observer=lambda *args: (_ for _ in ()).throw(OSError('metrics unavailable')))
        self.assertIn('ops://', broken.render(raw))
        self.assertIsNone(self.presenter.render(None))
        malformed = '{"session_id":1,"exit_code":null,"output":"\\ud800"}'
        self.assertEqual(self.presenter.render(malformed), malformed)
        self.assertEqual(self.events[-1][1], 'other')

    def test_nonbeneficial_and_small_unstructured_text_pass_through(self):
        raw = 'x' * 9000
        with patch('presentation_policy.Store') as factory:
            factory.return_value.capture.return_value = {'kind': 'reference', 'ref': 'ops://large', 'metadata': {}, 'preview': raw * 2}
            self.assertEqual(self.presenter.render(raw), raw)
            self.assertEqual(self.events[-1][1], 'not_beneficial')
        for raw in ('small', 'x' * 2048):
            self.assertEqual(self.presenter.render(raw), raw)
            self.assertEqual(self.events[-1][1], 'below_threshold')

    def test_progress_is_bounded_expires_and_does_not_guess_other_output_types(self):
        now = [0]
        progress = Progress(limit=2, ttl=3, clock=lambda: now[0])
        def poll(session):
            return analyze({'session_id': session, 'output': 'pending'})
        for session in (1, 2, 3):
            self.assertIsNone(progress.observe(poll(session)))
        self.assertIsNone(progress.observe(poll(1)))  # Oldest entry was evicted.
        now[0] = 5
        self.assertIsNone(progress.observe(poll(1)))
        for value in ('plain text', {'output': 'no identity'}, {'session_id': None, 'output': 'pending'},
                      {'session_id': '', 'output': 'pending'}, {'session_id': 'x' * 129, 'output': 'pending'}):
            self.assertIsNone(progress.observe(analyze(value)))


if __name__ == '__main__':
    unittest.main()
