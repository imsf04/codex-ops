import json
import os
import tempfile
import unittest
from unittest.mock import patch

import observation_metrics
from store import Store
from telemetry import snapshot
from presentation_policy import Presenter


class ObservationMetricsTests(unittest.TestCase):
    def test_producer_link_and_bounded_repeat_cost_survive_process_meter_close(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'CODEX_OPS_STORE': root}):
            store = Store(root)
            receipt = store.capture('x' * 12000)
            self.assertIs(observation_metrics.reference(receipt, {'tool': 'fixture.read', 'session': 'chat'}), receipt)
            page = store.result(receipt['ref'], view='raw', max_bytes=512)
            for _ in range(2):
                self.assertIs(observation_metrics.retrieval(page, ['raw', 0, 512]), page)
            stats = snapshot(root=root)
            self.assertEqual(stats['totals']['items'], 0)
            self.assertEqual(stats['retrievalCosts']['items'], 2)
            self.assertEqual(stats['retrievalCosts']['repeatedPageItems'], 1)
            self.assertIn('fixture.read', stats['retrievalCosts']['byTool'])
            self.assertEqual(len(stats['instances']), 1)
            store.close()

    def test_fail_open_and_nonreference_results_do_not_change_data(self):
        value = {'kind': 'inline', 'value': 1}
        self.assertIs(observation_metrics.reference(value, {}), value)
        self.assertIs(observation_metrics.retrieval(value, []), value)
        receipt = {'kind': 'reference', 'ref': 'ops://' + 'a' * 48}
        with patch.object(observation_metrics, 'Telemetry', side_effect=OSError('unavailable')):
            self.assertIs(observation_metrics.reference(receipt, {}), receipt)
        with patch.object(observation_metrics, 'Telemetry') as meter:
            meter.return_value.link_reference.side_effect = ValueError('bad')
            self.assertIs(observation_metrics.reference(receipt, {}), receipt)
            meter.return_value.close.assert_called_once()

    def test_daily_linkage_identity_does_not_keep_old_retrieval_counts_alive_forever(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'CODEX_OPS_STORE': root}):
            ref = 'ops://' + 'a' * 48
            result = {'ref': ref, 'view': 'raw', 'text': 'saved'}
            with patch('time.time', return_value=1000):
                observation_metrics.retrieval(result, ['raw', 0])
            with patch('time.time', return_value=1000 + 31 * 86400):
                observation_metrics.retrieval(result, ['raw', 0])
                self.assertEqual(snapshot(root=root)['retrievalCosts']['items'], 1)

    def test_presenter_links_only_new_receipts_and_keeps_display_on_link_failure(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'CODEX_OPS_STORE': root}):
            refs = []
            shown = Presenter(on_reference=refs.append).render('x' * 12000)
            self.assertEqual(refs, [json.loads(shown)['ref']])
            def fail(ref):
                raise OSError('offline')
            self.assertIn('ops://', Presenter(on_reference=fail).render('x' * 12000))
            presenter = Presenter(on_reference=refs.append)
            presenter._link('not json')
            self.assertEqual(len(refs), 1)


if __name__ == '__main__':
    unittest.main()
