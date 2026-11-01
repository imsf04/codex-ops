import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime_bridge'))
from manager import publish_status


class StatusPublicationTests(unittest.TestCase):
    def test_msix_cross_device_rename_still_publishes_fresh_status(self):
        error = OSError('MSIX redirected directory')
        error.winerror = 17
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '42.json'
            with patch('manager.os.replace', side_effect=error):
                publish_status(path, {'state': 'ready', 'updatedAt': 1})
                publish_status(path, {'state': 'ready', 'updatedAt': 2})
            self.assertEqual(json.loads(path.read_text()), {'state': 'ready', 'updatedAt': 2})
            self.assertFalse(path.with_suffix('.tmp').exists())

    def test_unrelated_io_errors_are_not_relabelled_as_msix(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('manager.os.replace', side_effect=PermissionError('denied')):
                with self.assertRaises(PermissionError):
                    publish_status(Path(folder) / '42.json', {'state': 'ready'})


if __name__ == '__main__':
    unittest.main()
