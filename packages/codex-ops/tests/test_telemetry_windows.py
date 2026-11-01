import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import telemetry
import telemetry_windows as windows


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def meter(self, origin='production'):
        meter = telemetry.Telemetry(self.root, origin=origin, context={'tool': 'read', 'session': 'session'})
        self.addCleanup(meter.close)
        return meter

    def record_at(self, meter, when, value=1000):
        with patch('telemetry.time.time', return_value=when):
            self.assertTrue(meter.record('text', 'compacted', value, value // 10))

    def at(self, when, window='hour', origin='production'):
        with patch('telemetry.time.time', return_value=when):
            return telemetry.snapshot(origin, self.root, window)

    def test_completed_bucket_boundaries_and_origin_separation(self):
        meter, validation = self.meter(), self.meter('validation')
        self.record_at(meter, 3599, 1000)
        self.record_at(meter, 3600, 2000)
        self.record_at(validation, 3599, 5000)
        before = self.at(3601)
        self.assertEqual(before['totals']['originalBytes'], 1000)
        self.assertEqual(before['window']['endExclusive'], 3600)
        self.assertTrue(before['window']['currentPartialBucketExcluded'])
        self.assertFalse(before['window']['historyAvailableForFullInterval'])
        after = self.at(3900)
        self.assertEqual(after['totals']['originalBytes'], 3000)
        self.assertEqual(self.at(7200)['totals']['originalBytes'], 2000)
        self.assertEqual(self.at(3900, origin='validation')['totals']['originalBytes'], 5000)
        self.assertEqual(self.at(3900, 'all')['totals']['originalBytes'], 3000)
        self.assertEqual(after['byTool']['read']['savedBytes'], 2700)

    def test_linked_retrieval_is_separate_and_repeated_page_is_measured(self):
        meter = self.meter()
        reference = 'ops://' + 'a' * 48
        with patch('telemetry.time.time', return_value=1000):
            meter.link_reference(reference)
            meter.record_retrieval(reference, 500, 'page')
            meter.record_retrieval(reference, 500, 'page')
        result = self.at(1200)
        self.assertEqual(result['totals']['items'], 0)
        self.assertEqual(result['retrievalCosts']['returnedBytes'], 1000)
        self.assertEqual(result['retrievalCosts']['repeatedPageBytes'], 500)
        self.assertEqual(result['retrievalCosts']['linkedItems'], 2)
        self.assertIn('read', result['retrievalCosts']['byTool'])
        self.assertEqual(result['byReason'], {})
        self.assertEqual(len(result['retrievalCosts']['bySession']), 1)

    def test_old_database_is_not_reconstructed_as_recent_history(self):
        db = sqlite3.connect(self.root / 'telemetry.sqlite3')
        db.executescript(telemetry.SCHEMA)
        with db:
            db.execute('INSERT INTO instances VALUES (?,?,?,?)', ('old', 'production', 10, 1000))
            db.execute('INSERT INTO counts VALUES (?,?,?,?,?,?,?)', ('old', 'production', 'text', 'compacted', 1, 9000, 100))
        db.close()
        self.assertFalse(self.at(1200)['available'])
        self.assertEqual(self.at(1200)['totals']['originalBytes'], 0)
        self.assertEqual(self.at(1200, 'all')['totals']['originalBytes'], 9000)
        meter = self.meter()
        self.assertFalse(self.at(1200)['available'])
        self.record_at(meter, 1000)
        self.assertEqual(self.at(1200)['totals']['originalBytes'], 1000)
        self.assertTrue(self.at(1200)['window']['legacyDataExcluded'])

    def test_dimension_overflow_preserves_total_and_reports_loss_of_attribution(self):
        meter = self.meter()
        with patch.object(windows, 'MAX_DIMENSIONS', 1), patch('telemetry.time.time', return_value=1000):
            meter.record('text', 'compacted', 100, 10, {'tool': 'first'})
            meter.record('notify', 'compacted', 200, 20, {'tool': 'second'})
            meter.record('text', 'compacted', 100, 10, {'tool': 'first'})
        result = self.at(1200)
        self.assertEqual(result['totals']['items'], 3)
        self.assertEqual(result['window']['dimensionOverflowItems'], 1)
        self.assertEqual(result['byTool']['unattributed']['originalBytes'], 200)
        self.assertEqual(result['attributionCoverage']['toolAttributedItems'], 2)

    def test_row_cap_and_retention_report_bounded_history(self):
        meter = self.meter()
        with patch.object(windows, 'MAX_ROWS', 2):
            for when in (1, 301, 601):
                self.record_at(meter, when)
        result = self.at(900)
        self.assertEqual(result['totals']['items'], 2)
        self.assertEqual(result['window']['prunedThrough'], 300)
        self.assertFalse(result['window']['historyAvailableForFullInterval'])
        later = windows.RETENTION_SECONDS + 1200
        self.record_at(meter, later)
        self.assertEqual(self.at(later + 300, 'week')['totals']['items'], 1)
        count = meter._db.execute('SELECT COUNT(*) FROM window_counts').fetchone()[0]
        self.assertEqual(count, 1)

    def test_empty_invalid_and_unavailable_windows_remain_honest(self):
        self.assertFalse(self.at(3600)['available'])
        with self.assertRaises(ValueError):
            self.at(3600, 'month')
        meter = self.meter()
        self.record_at(meter, 0)
        self.assertTrue(self.at(3600)['window']['historyAvailableForFullInterval'])
        self.assertEqual(self.at(3600, 'day')['window']['bucketSeconds'], 300)
        with patch.object(telemetry, '_snapshot', side_effect=sqlite3.OperationalError('busy')):
            self.assertFalse(self.at(3600)['available'])
        self.assertNotIn('session', json.dumps(self.at(3600)['bySession']))


if __name__ == '__main__':
    unittest.main()
