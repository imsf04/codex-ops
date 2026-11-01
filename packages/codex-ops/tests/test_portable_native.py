from pathlib import Path
import tempfile
import unittest

import files
import investigate


class PortableNativeTests(unittest.TestCase):
    def test_worker_reads_and_kernel_finds_the_same_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'source.py').write_text('PORTABLE_ANCHOR = 42\n', encoding='utf-8')
            read = files.run(str(root), 'read', {'files': [{'path': 'source.py'}]})
            self.assertEqual(read['status'], 'completed', read)
            self.assertIn('PORTABLE_ANCHOR = 42', str(read))
            result = investigate.run(str(root), {'question': 'Find PORTABLE_ANCHOR'}, files.run)
            self.assertEqual(result['evidenceState'], 'collected', result)
            self.assertTrue(any('PORTABLE_ANCHOR = 42' in row['text'] for row in result['items']))


if __name__ == '__main__':
    unittest.main()
