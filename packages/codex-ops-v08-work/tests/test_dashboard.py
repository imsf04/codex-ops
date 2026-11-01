"""Static export data, isolation and browser-safe embedding contracts."""
from contextlib import closing, redirect_stdout
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dashboard
from store import Store, TTL
import telemetry


def payload(html):
    return json.loads(re.search(r'<script id="snapshot" type="application/json">(.*?)</script>', html, re.S)[1])


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def meter(self, origin='production'):
        meter = telemetry.Telemetry(root=self.root, origin=origin, context={'tool': 'functions.exec', 'session': 'one'})
        self.addCleanup(meter.close)
        return meter

    def test_empty_read_only_export_does_not_create_data_directory(self):
        missing = self.root / 'missing'
        value = dashboard.collect(root=missing)
        self.assertFalse(value['presentation']['available'])
        self.assertFalse(value['cache']['available'])
        self.assertIsNone(value['newestSampleAt'])
        self.assertFalse(missing.exists())
        with patch.object(dashboard, 'default_root', return_value=missing):
            self.assertFalse(dashboard.collect()['cache']['available'])

    def test_stats_snapshot_keeps_origin_totals_and_retrieval_tables_separate(self):
        production, validation = self.meter(), self.meter('validation')
        production.record('text', 'compacted', 10000, 500)
        production.record_retrieval('ops://' + 'a' * 48, 1500, 'first')
        validation.record('text', 'compacted', 20000, 300)
        value = dashboard.collect(root=self.root)
        rendered = payload(dashboard.render(value))
        self.assertEqual(rendered['presentation']['totals']['originalBytes'], 10000)
        self.assertEqual(rendered['presentation']['retrievalCosts']['returnedBytes'], 1500)
        self.assertEqual(rendered['presentation']['byTool']['functions.exec']['savedBytes'], 9500)
        self.assertIsNotNone(rendered['newestSampleAt'])
        self.assertEqual(dashboard.collect('validation', self.root)['presentation']['totals']['originalBytes'], 20000)
        self.assertIn('not tokens', rendered['presentation']['measurement'])

    def test_cache_matches_store_summary_without_expiring_rows_or_reading_payload(self):
        store = Store(self.root)
        self.addCleanup(store.close)
        current = store.capture({'secret': 'private body'}, force=True)
        old = store.capture({'old': 'private old body'}, force=True)
        with store.db:
            store.db.execute('UPDATE observations SET created=? WHERE ref=?', (time.time() - TTL - 10, old['ref']))
        result = dashboard.collect(root=self.root)
        self.assertTrue(result['cache']['available'])
        self.assertEqual(result['cache']['liveReferences'], 1)
        self.assertEqual(result['cache']['liveBytes'], current['storedBytes'])
        self.assertEqual(store.db.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 2)
        self.assertNotIn('private body', json.dumps(result))
        with store.db:
            store.db.execute('DELETE FROM observations WHERE ref=?', (old['ref'],))
        expected = store.stats()
        self.assertEqual({k: result['cache'][k] for k in ('liveReferences', 'liveBytes', 'quotaBytes', 'ttlSeconds', 'counters')},
                         {k: expected[k] for k in ('liveReferences', 'liveBytes', 'quotaBytes', 'ttlSeconds', 'counters')})

    def test_unavailable_or_corrupt_cache_does_not_break_export(self):
        (self.root / 'observations.sqlite3').write_bytes(b'invalid SQLite')
        self.assertFalse(dashboard.cache_snapshot(self.root, time.time())['available'])
        with patch.object(dashboard, '_cache_snapshot', side_effect=OSError('denied')):
            self.assertFalse(dashboard.cache_snapshot(self.root, time.time())['available'])

    def test_hostile_labels_remain_json_data_and_no_external_assets_are_required(self):
        value = dashboard.collect(root=self.root)
        hostile = '</script><script>window.injected=true</script><img src="https://bad.invalid/">&\u2028'
        value['presentation']['byTool'] = {hostile: {'items': 1}}
        html = dashboard.render(value)
        self.assertNotIn(hostile, html)
        self.assertNotIn('</script><script>window.injected', html)
        self.assertEqual(payload(html)['presentation']['byTool'], value['presentation']['byTool'])
        tags = Tags()
        tags.feed(html)
        scripts = [attrs for tag, attrs in tags.tags if tag == 'script']
        self.assertEqual(len(scripts), 2)
        self.assertTrue(all('src' not in attrs for attrs in scripts))
        self.assertFalse(any(tag in ('img', 'iframe', 'link') for tag, _ in tags.tags))
        self.assertIn("td.textContent=", html)
        self.assertNotIn('.innerHTML', html)
        self.assertIn('aria-sort', html)
        self.assertIn("addEventListener('input'", html)
        self.assertIn("default-src 'none'", html)

    def test_cli_export_requires_absolute_html_and_writes_only_requested_file(self):
        output = self.root / 'reports' / 'stats.html'
        result = dashboard.export(output, 'validation', self.root / 'missing')
        self.assertFalse(result['networkRequired'])
        self.assertEqual(payload(output.read_text(encoding='utf-8'))['origin'], 'validation')
        for invalid in ('relative.html', str(self.root / 'stats.json')):
            with self.assertRaises(ValueError):
                dashboard.export(invalid, root=self.root)
        self.assertFalse((self.root / 'missing').exists())
        stream = io.StringIO()
        with redirect_stdout(stream):
            dashboard.main(['--output', str(output), '--origin', 'production', '--store', str(self.root / 'missing')])
        self.assertEqual(json.loads(stream.getvalue())['output'], str(output))

    def test_unknown_origin_is_rejected_before_writing_output(self):
        output = self.root / 'invalid.html'
        with self.assertRaises(ValueError):
            dashboard.export(output, 'other', self.root)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
