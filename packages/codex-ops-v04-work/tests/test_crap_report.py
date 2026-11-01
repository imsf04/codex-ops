from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from crap_report import crap, functions


class CrapTests(unittest.TestCase):
    def test_formula_known_points(self):
        self.assertEqual(crap(10, 1), 10)
        self.assertEqual(crap(10, 0), 110)
        self.assertEqual(crap(10, 0.5), 22.5)

    def test_invalid_fraction_is_rejected(self):
        for value in (-0.1, 1.1):
            with self.assertRaises(ValueError):
                crap(3, value)

    def test_threshold_uses_unrounded_score(self):
        value = crap(6, 0.99)
        self.assertGreater(value, 6)
        self.assertEqual(round(value, 3), 6)

    def test_nested_scopes_are_named_and_methods_are_counted_once(self):
        source = 'class A:\n def outer(self):\n  def inner(x):\n   return x if x else 0\n  return inner(1)\n'
        found = functions(source)
        self.assertEqual([name for name, _ in found], ['A.outer', 'A.outer.inner'])
        self.assertEqual(found[1][1].complexity, 2)


if __name__ == '__main__':
    unittest.main()
