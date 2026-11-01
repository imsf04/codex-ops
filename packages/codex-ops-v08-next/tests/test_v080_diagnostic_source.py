"""Real native source reads for explicit source= coordinates in failure logs."""
import tempfile
from pathlib import Path
import unittest

import files
import workflow


class ExplicitSourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'src').mkdir()
        self.source = self.root / 'src/export.py'
        self.source.write_text('SCHEMA = 3\nraise ValueError("EXPORT_SCHEMA")\n', encoding='utf-8')
        self.calls = []

    def invoke(self, root, operation, args):
        self.calls.append((operation, args))
        return files.run(root, operation, args)

    def diagnose(self, args):
        return workflow.run(str(self.root), 'diagnose', args, 'source-coordinate-test', invoke=self.invoke)

    def test_late_log_source_assignment_reads_actual_file_and_keeps_both_coordinates(self):
        line = 'ERROR EXPORT_SCHEMA expected=3 observed=2 source=src/export.py:2'
        log = self.root / 'build.log'
        log.write_text('INFO checks passed\n' * 5000 + line + '\n', encoding='utf-8')
        before = log.read_bytes(), self.source.read_bytes()
        result = self.diagnose({'logPath': 'build.log'})
        self.assertEqual(result['diagnostics'], [{'line': 5001, 'text': line, 'clipped': False}])
        self.assertEqual(result['sourceRequests'][0]['path'], str(self.source))
        context = result['context']['items'][0]
        self.assertEqual(context['status'], 'completed')
        self.assertEqual(context['items'][1]['line'], 2)
        self.assertEqual(context['items'][1]['text'], 'raise ValueError("EXPORT_SCHEMA")')
        self.assertEqual([name for name, _ in self.calls], ['stat', 'grep', 'read'])
        self.assertEqual((log.read_bytes(), self.source.read_bytes()), before)

    def test_quoted_and_unicode_space_paths_preserve_filename(self):
        path = self.root / 'src/导出 rules.py'
        path.write_text('SCHEMA = 3\nraise RuntimeError("test")\n', encoding='utf-8')
        for coordinate in ('"src/导出 rules.py:2"', '"src/导出 rules.py":2',
                           'src/导出 rules.py:2', f'"{path}":2:4'):
            with self.subTest(coordinate=coordinate):
                result = self.diagnose({'log': 'ERROR expected=3 source=' + coordinate})
                self.assertEqual(result['sourceRequests'][0]['path'], str(path))
                self.assertEqual(result['context']['items'][0]['status'], 'completed')

    def test_source_assignment_cannot_escape_root_or_read_credential_named_file(self):
        escaped = self.diagnose({'log': 'ERROR source=../outside.py:2'})
        self.assertEqual(escaped['outsideRootLocations'], 1)
        self.assertEqual(escaped['sourceRequests'], [])
        self.assertEqual(self.calls, [])
        (self.root / '.env').write_text('TEST_FIXTURE_ONLY=1\n', encoding='utf-8')
        restricted = self.diagnose({'log': 'ERROR source=.env:2'})
        self.assertEqual(restricted['context']['status'], 'partial')
        self.assertEqual(restricted['context']['items'][0]['error']['code'], 'CREDENTIAL_DENIED')
        self.assertNotIn('TEST_FIXTURE_ONLY', str(restricted))


if __name__ == '__main__':
    unittest.main()
