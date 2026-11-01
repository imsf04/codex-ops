"""Directory identity authorization under concurrent POSIX path replacement."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mutations import task_directories


@unittest.skipUnless(os.name == 'posix', 'POSIX descriptor authority; Windows uses rename exclusion')
class PosixDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_create_and_remove_use_the_opened_parent_after_replacement(self):
        for create in (True, False):
            with self.subTest(create=create):
                case = self.root / str(create)
                parent, outside, moved = case / 'parent', case / 'outside', case / 'moved'
                parent.mkdir(parents=True)
                outside.mkdir()
                if not create:
                    (parent / 'child').mkdir()
                    (outside / 'child').mkdir()
                original = task_directories._hold

                @contextmanager
                def relocate(path):
                    with original(path) as descriptor:
                        parent.rename(moved)
                        parent.symlink_to(outside, target_is_directory=True)
                        yield descriptor

                with patch.object(task_directories, '_hold', relocate):
                    task_directories.execute(case, 'parent/child', create)
                self.assertEqual((moved / 'child').exists(), create)
                self.assertEqual((outside / 'child').exists(), not create)

    def test_open_rejects_symlinks_in_each_component(self):
        actual = self.root / 'actual'
        (actual / 'inner').mkdir(parents=True)
        alias = self.root / 'alias'
        alias.symlink_to(actual, target_is_directory=True)
        for path in (alias, alias / 'inner'):
            with self.subTest(path=path), self.assertRaises(OSError):
                with task_directories._hold(path):
                    self.fail('A symlink was traversed')

    def test_directory_handle_is_closed_even_when_operation_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            with task_directories._hold(self.root) as descriptor:
                self.assertEqual(os.fstat(descriptor).st_ino, self.root.stat().st_ino)
                raise RuntimeError('injected')
        with self.assertRaises(OSError):
            os.fstat(descriptor)

    def test_rmdir_never_follows_a_replaced_leaf_symlink(self):
        outside = self.root / 'outside'
        outside.mkdir()
        leaf = self.root / 'leaf'
        leaf.mkdir()
        original = task_directories._hold

        @contextmanager
        def replace_leaf(path):
            with original(path) as descriptor:
                leaf.rmdir()
                leaf.symlink_to(outside, target_is_directory=True)
                yield descriptor

        with patch.object(task_directories, '_hold', replace_leaf), self.assertRaises(OSError):
            task_directories.execute(self.root, 'leaf', False)
        self.assertTrue(outside.is_dir())
        self.assertTrue(leaf.is_symlink())
