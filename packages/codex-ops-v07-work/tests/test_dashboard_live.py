from contextlib import redirect_stdout
import http.client
import io
import json
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import dashboard
import dashboard_server
import task_snapshot


class LiveDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def journal(self, number, phase='ready'):
        identity = f'{number:032x}'
        path = self.root / '.codex-ops-mutations' / identity
        path.mkdir(parents=True)
        value = {'id': identity, 'phase': phase, 'plan': {'items': [{'content': 'SECRET'}]},
                 'error': 'SECRET ERROR', 'backups': {'private': 'SECRET'}}
        (path / 'journal.json').write_text(json.dumps(value))
        return path

    def test_tasks_are_explicit_bounded_journal_metadata_only(self):
        self.assertFalse(task_snapshot.snapshot()['enabled'])
        self.assertEqual(task_snapshot.snapshot(str(self.root))['items'], [])
        for number, phase in enumerate(('ready', 'needs-inspection', 'completed')):
            self.journal(number, phase)
        value = task_snapshot.snapshot(str(self.root))
        self.assertEqual(len(value['items']), 3)
        self.assertTrue(value['complete'])
        self.assertNotIn('SECRET', json.dumps(value))
        self.assertTrue(all(row['hasError'] for row in value['items']))
        with patch.object(task_snapshot, 'MAX_TASKS', 2):
            self.assertFalse(task_snapshot.snapshot(str(self.root))['complete'])
        with patch.object(task_snapshot, 'MAX_SCAN', 2):
            self.assertFalse(task_snapshot.snapshot(str(self.root))['complete'])
        with patch.object(task_snapshot, 'MAX_BYTES', 100):
            bounded = task_snapshot.snapshot(str(self.root))
            self.assertEqual(bounded['items'], [])
            self.assertEqual(bounded['rejectedEntries'], 3)

    def test_corrupt_missing_linked_and_growing_journals_are_not_followed(self):
        path = self.journal(1)
        for raw in ('[]', '{}', '{"id":"bad","phase":"ready"}', 'invalid'):
            (path / 'journal.json').write_text(raw)
            self.assertFalse(task_snapshot.snapshot(str(self.root))['complete'])
        (path / 'journal.json').unlink()
        self.assertEqual(task_snapshot.snapshot(str(self.root))['rejectedEntries'], 1)
        self.assertFalse(task_snapshot.snapshot('relative')['complete'])
        fake = MagicMock()
        for mode, attrs in ((stat.S_IFLNK, 0), (stat.S_IFREG, 0x400), (stat.S_IFDIR, 0)):
            fake.lstat.return_value = SimpleNamespace(st_mode=mode, st_file_attributes=attrs)
            with self.assertRaises(ValueError):
                task_snapshot._regular(fake)
        fake.lstat.return_value = SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0, st_size=1, st_mtime=0)
        fake.open.return_value.__enter__.return_value.read.return_value = b'123'
        budget = task_snapshot._ByteBudget(2)
        with self.assertRaises(ValueError):
            task_snapshot._summary(fake, 'x', budget)
        self.assertEqual(budget.remaining, -1)

    def test_invalid_journals_charge_actual_bytes_and_stop_at_shared_budget(self):
        for number in range(12):
            path = self.journal(number)
            # Invalid JSON still incurs IO and must consume the shared budget.
            (path / 'journal.json').write_bytes(b'x' * 100)
        original_open = Path.open
        reads = []
        class CountingReader:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def read(self, limit):
                data = self.stream.read(limit)
                reads.append(len(data))
                return data
            def fileno(self):
                return self.stream.fileno()
        def tracked(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            return CountingReader(stream) if args == ('rb',) else stream
        with patch.object(task_snapshot, 'MAX_BYTES', 300), patch.object(Path, 'open', tracked):
            result = task_snapshot.snapshot(str(self.root))
        self.assertEqual(reads, [100, 100, 100])
        self.assertEqual(sum(reads), 300)
        self.assertEqual(result['rejectedEntries'], 3)
        self.assertFalse(result['complete'])

    def test_growth_rejection_also_consumes_read_bytes_without_reading_past_budget(self):
        path = self.journal(1) / 'journal.json'
        path.write_bytes(b'x' * 40)
        budget = task_snapshot._ByteBudget(100)
        with patch.object(task_snapshot.os, 'fstat', return_value=SimpleNamespace(st_size=101)):
            with self.assertRaisesRegex(ValueError, 'grew'):
                budget.read(path)
        self.assertEqual(budget.remaining, 60)
        fake = MagicMock()
        fake.lstat.return_value = SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0, st_size=1, st_mtime=0)
        fake.open.return_value.__enter__.return_value.read.side_effect = OSError('partial IO failure')
        with self.assertRaises(OSError):
            budget.read(fake)
        self.assertEqual(budget.remaining, 0)

    def listener(self, collector=None):
        collect = collector or (lambda: dashboard.collect(root=self.root))
        server = dashboard_server.server(collect, dashboard.render)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 3)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def request(self, server, path='/', method='GET', headers=None):
        client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        try:
            client.request(method, path, headers=headers or {})
            response = client.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            client.close()

    def test_http_refresh_reads_new_snapshot_and_exposes_no_mutations_or_files(self):
        calls = []
        def collect():
            calls.append(True)
            return {**dashboard.collect(root=self.root), 'live': True, 'sequence': len(calls)}
        server = self.listener(collect)
        status, body, headers = self.request(server, '/snapshot')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['sequence'], 1)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(json.loads(self.request(server, '/snapshot')[1])['sequence'], 2)
        self.assertIn(b'location.reload()', self.request(server)[1])
        for path in ('/secret', '/snapshot?root=other', '/' + 'x' * 600, '/#fragment'):
            self.assertEqual(self.request(server, path)[0], 404)
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            self.assertEqual(self.request(server, method=method)[0], 405)
        self.assertFalse((self.root / 'telemetry.sqlite3').exists())

    def test_http_rejects_external_browser_origins_and_hostnames(self):
        server = self.listener()
        for headers in ({'Host': 'attacker.test'}, {'Origin': 'https://attacker.test'}, {'Origin': 'null'}):
            self.assertEqual(self.request(server, headers=headers)[0], 403)
        origin = 'http://127.0.0.1:' + str(server.server_port)
        self.assertEqual(self.request(server, headers={'Origin': origin})[0], 200)
        for port in (-1, 65536, True):
            with self.assertRaises(ValueError):
                dashboard_server.server(lambda: {}, lambda _: '', port)
        with self.assertRaises(ValueError):
            dashboard.collect(root=self.root, window='invalid')

    def test_unavailable_snapshot_and_explicit_cli_serve_lifecycle(self):
        def unavailable():
            raise OSError('offline')
        server = self.listener(unavailable)
        self.assertEqual(self.request(server)[0], 503)
        with patch.object(dashboard_server, 'server') as factory:
            listener = factory.return_value.__enter__.return_value
            listener.server_port = 1234
            listener.serve_forever.side_effect = KeyboardInterrupt
            with redirect_stdout(io.StringIO()) as output:
                dashboard.main(['--serve', '--window', 'hour', '--store', str(self.root), '--tasks-root', str(self.root)])
            self.assertTrue(json.loads(output.getvalue())['readOnly'])
            self.assertTrue(factory.call_args.args[0]()['live'])
        self.assertFalse((self.root / '.codex-ops-mutations').exists())


if __name__ == '__main__':
    unittest.main()
