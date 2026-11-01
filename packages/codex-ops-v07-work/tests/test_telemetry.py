import concurrent.futures
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import telemetry


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.instances = []

    def tearDown(self):
        for instance in self.instances:
            instance.close()
        self.temp.cleanup()

    def create(self, **kwargs):
        instance = telemetry.Telemetry(root=self.root, **kwargs)
        self.instances.append(instance)
        return instance

    def test_record_aggregate_and_readback_reason_preserve_precise_byte_accounting(self):
        meter = self.create(instance_id='one')
        self.assertTrue(meter.record('text', 'compacted', 10000, 1000))
        self.assertTrue(meter.record('notify', 'below_threshold', 10, 10))
        self.assertTrue(meter.record('wait', 'explicit_retrieval', 500, 500))
        value = telemetry.snapshot(root=self.root)
        self.assertTrue(value['available'])
        self.assertEqual(value['totals'], {'items': 3, 'originalBytes': 10510, 'presentedBytes': 1510, 'savedBytes': 9000})
        self.assertEqual(value['byChannel']['text']['savedBytes'], 9000)
        self.assertEqual(value['byReason']['explicit_retrieval']['presentedBytes'], 500)
        self.assertEqual(value['instances'][0]['instanceId'], 'one')
        self.assertIn('not tokens', value['measurement'])

    def test_persistence_across_closed_connections_and_distinct_origins(self):
        first = self.create(instance_id='stable')
        first.record('text', 'compacted', 100, 20)
        first.close()
        restarted = self.create(instance_id='stable')
        restarted.record('text', 'compacted', 200, 40)
        validation = self.create(instance_id='stable', origin='validation')
        validation.record('text', 'compacted', 999, 1)
        self.assertEqual(telemetry.snapshot(root=self.root)['totals']['originalBytes'], 300)
        self.assertEqual(telemetry.snapshot('validation', self.root)['totals']['originalBytes'], 999)
        self.assertEqual(len(telemetry.snapshot(root=self.root)['instances']), 1)

    def test_concurrent_records_have_no_lost_updates(self):
        first, second = self.create(), self.create()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            values = list(executor.map(lambda n: (first, second)[n % 2].record('text', 'compacted', 100, 10), range(120)))
        self.assertTrue(all(values))
        self.assertNotEqual(first.instance_id, second.instance_id)
        self.assertEqual(telemetry.snapshot(root=self.root)['totals']['items'], 120)
        self.assertEqual(telemetry.snapshot(root=self.root)['totals']['savedBytes'], 10800)

    def test_unknown_labels_do_not_persist_payloads_or_grow_group_cardinality(self):
        meter = self.create()
        for suffix in range(20):
            self.assertTrue(meter.record('secret-command-' + str(suffix), 'private-content-' + str(suffix), 100, 20))
        meter.close()
        value = telemetry.snapshot(root=self.root)
        self.assertEqual(list(value['byChannel']), ['other'])
        self.assertEqual(list(value['byReason']), ['other'])
        with closing(sqlite3.connect(self.root / 'telemetry.sqlite3')) as db:
            rows = db.execute('SELECT channel,reason,items FROM counts').fetchall()
            columns = [r[1] for r in db.execute('PRAGMA table_info(counts)')]
        self.assertEqual(rows, [('other', 'other', 20)])
        self.assertNotIn('payload', columns)
        self.assertNotIn('secret-command', json.dumps(value))

    def test_retention_prunes_expired_instances_with_their_aggregates(self):
        with patch.object(telemetry, 'RETENTION_SECONDS', 10):
            with patch.object(telemetry.time, 'time', return_value=100):
                self.create(instance_id='old').record('text', 'compacted', 1000, 100)
            with patch.object(telemetry.time, 'time', return_value=111):
                # Read-only snapshots also hide expired entries before a writer prunes.
                self.assertEqual(telemetry.snapshot(root=self.root)['totals']['items'], 0)
                self.create(instance_id='new').record('text', 'compacted', 20, 10)
                self.assertEqual(telemetry.snapshot(root=self.root)['totals']['originalBytes'], 20)
            with closing(sqlite3.connect(self.root / 'telemetry.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT instance_id FROM counts').fetchall(), [('new',)])

    def test_instance_bound_is_per_origin_and_resurrected_active_writer_is_retained(self):
        with patch.object(telemetry, 'MAX_INSTANCES', 2):
            for n in range(3):
                with patch.object(telemetry.time, 'time', return_value=100 + n):
                    self.create(instance_id=str(n)).record('text', 'compacted', 10, 1)
            with patch.object(telemetry.time, 'time', return_value=103):
                self.create(origin='validation').record('text', 'compacted', 100, 1)
                value = telemetry.snapshot(root=self.root)
                self.assertEqual([r['instanceId'] for r in value['instances']], ['2', '1'])
                self.assertEqual(value['totals']['items'], 2)
                self.assertTrue(self.instances[0].record('text', 'compacted', 20, 2))
                self.assertEqual(telemetry.snapshot(root=self.root)['totals']['originalBytes'], 30)

    def test_closed_missing_and_unavailable_storage_fail_open(self):
        missing = self.root / 'missing'
        self.assertFalse(telemetry.snapshot(root=missing)['available'])
        self.assertFalse(missing.exists())
        meter = self.create()
        meter.close()
        self.assertFalse(meter.record('text', 'compacted', 10, 1))
        self.assertEqual(meter.dropped_records, 1)
        blocked = self.root / 'file'
        blocked.write_text('not a directory')
        unavailable = telemetry.Telemetry(root=blocked)
        self.instances.append(unavailable)
        self.assertFalse(unavailable.record('text', 'compacted', 10, 1))
        self.assertFalse(telemetry.snapshot(root=blocked)['available'])

    def test_sqlite_open_record_close_and_read_failures_are_reported_without_throwing(self):
        with patch.object(telemetry, '_register', side_effect=sqlite3.OperationalError('readonly')):
            meter = self.create()
        self.assertFalse(meter.record('text', 'compacted', 10, 1))
        good = self.create()
        with patch.object(good, '_persist', side_effect=sqlite3.OperationalError('busy')):
            self.assertFalse(good.record('text', 'compacted', 10, 1))
        self.assertEqual(good.dropped_records, 1)
        with patch.object(telemetry, '_snapshot', side_effect=sqlite3.DatabaseError('corrupt')):
            self.assertFalse(telemetry.snapshot(root=self.root)['available'])
        with patch.object(telemetry, '_path', side_effect=OSError('denied')):
            self.assertFalse(telemetry.snapshot(root=self.root)['available'])
        db = MagicMock()
        db.executescript.side_effect = sqlite3.DatabaseError('schema')
        with patch.object(telemetry.sqlite3, 'connect', return_value=db):
            self.assertFalse(self.create().record('text', 'compacted', 1, 1))
        db.close.assert_called_once()
        broken = self.create()
        original = broken._db
        original.close()
        broken._db = MagicMock()
        broken._db.close.side_effect = sqlite3.DatabaseError('close failure')
        broken.close()
        self.assertIsNone(broken._db)

    def test_environment_origin_default_and_invalid_configuration(self):
        with patch.dict(os.environ, {'CODEX_OPS_STORE': str(self.root), 'CODEX_OPS_MEASUREMENT_ORIGIN': 'validation'}):
            meter = telemetry.Telemetry()
            self.instances.append(meter)
            self.assertEqual(meter.origin, 'validation')
            meter.record('notify', 'compacted', 100, 10)
            self.assertEqual(telemetry.snapshot('validation')['totals']['items'], 1)
        with self.assertRaises(ValueError):
            self.create(origin='unknown')
        with self.assertRaises(ValueError):
            telemetry.snapshot('unknown', self.root)

    def test_invalid_counts_are_not_written_and_expansion_is_not_hidden(self):
        meter = self.create()
        for before, after in [(-1, 0), (1, -1), (True, 0), (1, 1.5)]:
            self.assertFalse(meter.record('text', 'compacted', before, after))
        self.assertEqual(meter.dropped_records, 4)
        self.assertTrue(meter.record('error', 'error_preserved', 10, 20))
        self.assertEqual(telemetry.snapshot(root=self.root)['totals']['savedBytes'], -10)


if __name__ == '__main__':
    unittest.main()
