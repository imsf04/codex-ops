import hashlib
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import cache_reader
import readonly_snapshot
from store import Store


class CacheReaderTests(unittest.TestCase):
    def test_existing_reference_read_keeps_database_bytes_and_directory_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            receipt = store.capture({'value': 'plan-body'}, force=True)
            store.close()
            root = Path(folder)
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
            self.assertEqual(cache_reader.load(receipt['ref'], folder), {'value': 'plan-body'})
            self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}, before)
            with patch.object(cache_reader, 'default_root', return_value=root):
                self.assertEqual(cache_reader.load(receipt['ref'])['value'], 'plan-body')

    def test_missing_invalid_and_expired_references_do_not_create_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            absent = Path(folder) / 'absent'
            for ref in (None, 'invalid', 'ops://' + 'f' * 48):
                with self.assertRaises(ValueError):
                    cache_reader.load(ref, absent)
            self.assertFalse(absent.exists())
            store = Store(folder)
            ref = store.capture('expired', force=True)['ref']
            store.db.execute('UPDATE observations SET created=?', (time.time() - 90000,))
            store.db.commit()
            store.close()
            for key in (ref, 'ops://' + 'f' * 48):
                with self.assertRaises(ValueError):
                    cache_reader.load(key, folder)

    def test_busy_writer_and_oversized_database_fail_before_plan_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            ref = store.capture('saved', force=True)['ref']
            store.db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(ValueError):
                cache_reader.load(ref, folder)
            store.db.rollback()
            store.close()
            with patch.object(readonly_snapshot, 'MAX_BYTES', 1), self.assertRaises(ValueError):
                cache_reader.load(ref, folder)

    def test_uncheckpointed_wal_is_recovered_only_in_private_copy(self):
        import subprocess, sys
        with tempfile.TemporaryDirectory() as folder:
            code = 'from store import Store;import os;s=Store(' + repr(folder) + ');r=s.capture("wal-body",force=True);print(r["ref"],flush=True);os._exit(0)'
            result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
            ref = result.stdout.strip()
            self.assertTrue((Path(folder) / 'observations.sqlite3-wal').exists())
            before = {p.name: p.stat().st_size for p in Path(folder).iterdir()}
            self.assertEqual(cache_reader.load(ref, folder), 'wal-body')
            self.assertEqual({p.name: p.stat().st_size for p in Path(folder).iterdir()}, before)


if __name__ == '__main__':
    unittest.main()
