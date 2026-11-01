"""Observable attribution, migration and retrieval-cost contracts."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import telemetry
import telemetry_details as details

REF = 'ops://' + 'a' * 48
OTHER = 'ops://' + 'b' * 48


class AttributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.meters = []

    def tearDown(self):
        for meter in self.meters:
            meter.close()
        self.temp.cleanup()

    def meter(self, **kwargs):
        meter = telemetry.Telemetry(root=self.root, **kwargs)
        self.meters.append(meter)
        return meter

    def snapshot(self, origin='production'):
        return telemetry.snapshot(origin, self.root)

    def test_exact_source_context_and_private_session_ids(self):
        meter = self.meter(context={'tool': 'functions.exec', 'session': 'private-thread-A'})
        self.assertTrue(meter.record('text', 'compacted', 1000, 100))
        meter.record('wait', 'frame_repeat', 600, 60, context={'tool': 'functions.wait', 'session': 'private-thread-B'})
        meter.record('text', 'below_threshold', 10, 10, context={})
        value = self.snapshot()
        self.assertEqual(value['byTool']['functions.exec']['savedBytes'], 900)
        self.assertEqual(value['byTool']['functions.wait']['savedBytes'], 540)
        self.assertEqual(value['byReason']['frame_repeat']['items'], 1)
        self.assertEqual(value['bySession'][details.digest('private-thread-A')]['originalBytes'], 1000)
        self.assertEqual(value['attributionCoverage'], {'toolAttributedItems': 2, 'sessionAttributedItems': 2})
        self.assertNotIn('private-thread', json.dumps(value))
        meter.close()
        self.assertNotIn(b'private-thread', (self.root / 'telemetry.sqlite3').read_bytes())

    def test_untrusted_shapes_and_unbounded_labels_become_unattributed(self):
        invalid = [None, 'command', [], {'tool': []}, {'tool': 'command with args', 'session': 7},
                   {'tool': 'x' * 129, 'session': 'y' * 1025}, {'tool': '', 'session': ''}]
        for context in invalid:
            self.assertEqual(details.context(context), ('unattributed', 'unattributed'))
        self.assertEqual(details.context({'tool': 'mcp__server__tool', 'session': '\ud800'})[0], 'mcp__server__tool')
        meter = self.meter()
        meter.record('text', 'compacted', 10, 1, context=invalid[4])
        self.assertEqual(self.snapshot()['byTool']['unattributed']['items'], 1)

    def test_same_page_retrieval_cost_is_separate_from_emitted_bytes_and_cross_process(self):
        producer = self.meter(context={'tool': 'functions.exec', 'session': 'source-thread'})
        producer.record('text', 'compacted', 10000, 500)
        self.assertTrue(producer.link_reference(REF))
        producer.close()
        consumer = self.meter(context={'tool': 'mcp__codex_ops__ops_result', 'session': 'reader-thread'})
        page = json.dumps({'view': 'items', 'offset': 0, 'query': 'secret-search'})
        for size in (500, 700):
            self.assertTrue(consumer.record_retrieval(REF, size, page))
        consumer.record_retrieval(REF, 300, page + 'different')
        value = self.snapshot()
        self.assertEqual(value['totals']['presentedBytes'], 500)
        costs = value['retrievalCosts']
        self.assertEqual(costs['items'], 3)
        self.assertEqual(costs['returnedBytes'], 1500)
        self.assertEqual(costs['repeatedPageItems'], 1)
        self.assertEqual(costs['repeatedPageBytes'], 700)
        self.assertEqual(costs['linkedItems'], 3)
        self.assertEqual(costs['byTool']['functions.exec']['returnedBytes'], 1500)
        self.assertEqual(costs['bySession'][details.digest('source-thread')]['items'], 3)
        consumer.close()
        raw = (self.root / 'telemetry.sqlite3').read_bytes()
        for secret in (b'secret-search', REF.encode(), b'source-thread', b'reader-thread'):
            self.assertNotIn(secret, raw)

    def test_origin_isolation_and_unknown_source_fallback(self):
        producer = self.meter(context={'tool': 'functions.exec'})
        producer.link_reference(REF)
        producer.record_retrieval(REF, 100, 'page')
        validation = self.meter(origin='validation')
        validation.record_retrieval(REF, 200, 'page')
        result = self.snapshot('validation')['retrievalCosts']
        self.assertEqual(result['returnedBytes'], 200)
        self.assertEqual(result['repeatedPageItems'], 0)
        self.assertEqual(result['linkedItems'], 0)
        self.assertEqual(result['byTool']['unattributed']['items'], 1)
        self.assertEqual(self.snapshot()['retrievalCosts']['returnedBytes'], 100)

    def test_legacy_read_only_snapshot_and_additive_migration_preserve_totals(self):
        with closing(sqlite3.connect(self.root / 'telemetry.sqlite3')) as db:
            db.executescript(telemetry.SCHEMA)
            db.execute('INSERT INTO instances VALUES (?,?,?,?)', ('old', 'production', time.time(), time.time()))
            db.execute('INSERT INTO counts VALUES (?,?,?,?,?,?,?)', ('old', 'production', 'text', 'compacted', 2, 1000, 200))
            db.commit()
        before = self.snapshot()
        self.assertTrue(before['available'])
        self.assertEqual(before['byTool']['unattributed']['originalBytes'], 1000)
        meter = self.meter(instance_id='old', context={'tool': 'functions.exec'})
        meter.record('text', 'compacted', 500, 100)
        after = self.snapshot()
        self.assertEqual(after['totals']['originalBytes'], 1500)
        self.assertEqual(after['byTool']['unattributed']['items'], 2)
        self.assertEqual(after['byTool']['functions.exec']['items'], 1)
        # A still-running 0.3 writer can add counts; the unassigned remainder stays honest.
        with meter._db:
            meter._db.execute('UPDATE counts SET items=items+1,original_bytes=original_bytes+100,presented_bytes=presented_bytes+100')
        self.assertEqual(self.snapshot()['byTool']['unattributed']['items'], 3)

    def test_dimension_bound_preserves_totals_and_existing_labels(self):
        meter = self.meter()
        with patch.object(details, 'MAX_DIMENSIONS', 2):
            for n in range(4):
                context = {'tool': f'tool{n}', 'session': str(n)}
                meter.record('text', 'compacted', 100, 10, context=context)
                meter.record_retrieval(REF, 30, str(n), context=context)
            meter.record('text', 'compacted', 100, 10, context={'tool': 'tool0', 'session': '0'})
        value = self.snapshot()
        self.assertEqual(value['totals']['items'], 5)
        self.assertEqual(value['byTool']['tool0']['items'], 2)
        self.assertEqual(value['byTool']['unattributed']['items'], 2)
        self.assertEqual(len(value['byTool']), 3)
        self.assertEqual(value['retrievalCosts']['byTool']['unattributed']['items'], 2)

    def test_ref_and_page_retention_bounds_make_repeat_detection_explicitly_bounded(self):
        meter = self.meter(context={'tool': 'functions.exec'})
        with patch.object(details, 'MAX_REFERENCES', 1), patch.object(details, 'MAX_PAGES', 1):
            meter.link_reference(REF)
            meter.link_reference(OTHER)
            meter.record_retrieval(REF, 10, 'first', context={})
            meter.record_retrieval(OTHER, 20, 'second')
            meter.record_retrieval(REF, 30, 'first', context={})
        value = self.snapshot()['retrievalCosts']
        self.assertEqual(value['linkedItems'], 1)
        self.assertEqual(value['repeatedPageItems'], 0)
        self.assertEqual(value['byTool']['unattributed']['returnedBytes'], 40)
        with patch.object(details, 'RETENTION_SECONDS', 1), patch.object(telemetry.time, 'time', return_value=time.time() + 5):
            meter.record_retrieval(OTHER, 40, 'second', context={})
        self.assertEqual(self.snapshot()['retrievalCosts']['linkedItems'], 1)

    def test_link_ambiguity_is_sticky_and_expired_instance_prunes_detail_counters(self):
        with patch.object(telemetry.time, 'time', return_value=100):
            old = self.meter(context={'tool': 'old'})
            old.link_reference(REF)
            old.link_reference(REF, context={'tool': 'updated'})
            old.link_reference(REF, context={'tool': 'updated'})
            old.record('text', 'compacted', 10, 1)
            old.record_retrieval(REF, 10, 'page')
            self.assertEqual(self.snapshot()['retrievalCosts']['byTool']['unattributed']['items'], 1)
        with patch.object(telemetry, 'RETENTION_SECONDS', 10), patch.object(telemetry.time, 'time', return_value=111):
            self.meter().record('text', 'below_threshold', 1, 1)
            self.assertEqual(self.snapshot()['retrievalCosts']['items'], 0)
            with closing(sqlite3.connect(self.root / 'telemetry.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM retrieval_counts').fetchone()[0], 0)

    def test_identical_repeated_reference_link_retains_proven_source(self):
        meter = self.meter(context={'tool': 'functions.exec'})
        meter.link_reference(REF)
        meter.link_reference(REF)
        meter.record_retrieval(REF, 10, 'page')
        self.assertEqual(self.snapshot()['retrievalCosts']['byTool']['functions.exec']['items'], 1)

    def test_bad_reference_page_and_failed_writes_do_not_block_source_work(self):
        meter = self.meter()
        for ref in ('invalid', None, 'ops://' + 'z' * 48):
            self.assertFalse(meter.link_reference(ref))
            self.assertFalse(meter.record_retrieval(ref, 10, 'page'))
        for size in (-1, True, 0.5):
            self.assertFalse(meter.record_retrieval(REF, size, 'page'))
        for page in (None, [], 'x' * 65537):
            self.assertFalse(meter.record_retrieval(REF, 10, page))
        with patch.object(details, 'retrieve', side_effect=sqlite3.OperationalError('busy')):
            self.assertFalse(meter.record_retrieval(REF, 10, 'page'))
        self.assertEqual(self.snapshot()['retrievalCosts']['items'], 0)
        meter.close()
        self.assertFalse(meter.link_reference(REF))
        self.assertFalse(meter.record_retrieval(REF, 10, 'page'))


if __name__ == '__main__':
    unittest.main()
