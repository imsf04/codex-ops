"""Focused deterministic presentation gate; no external model calls."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
suite = unittest.TestSuite()
for pattern in ('test_presentation*.py', 'test_semantic_preview.py', 'test_frame_dedup.py',
                'test_v06_presentation.py', 'test_core.py', 'test_observation_architecture.py',
                'test_structured_preview.py'):
    suite.addTests(unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern=pattern))
result = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
