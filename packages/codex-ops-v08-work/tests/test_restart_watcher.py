import importlib.util
import json
from pathlib import Path
import sys
import unittest

folder = Path(__file__).resolve().parents[1] / 'runtime_bridge'
sys.path.insert(0, str(folder))
spec = importlib.util.spec_from_file_location('restart_watcher', folder / 'restart_after_turn.py')
watcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watcher)


class RestartWatcherTests(unittest.TestCase):
    def test_only_exact_completed_turn_can_trigger_quit(self):
        value = {'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': 'owned'}}
        self.assertTrue(watcher.completed(json.dumps(value), 'owned'))
        self.assertFalse(watcher.completed(json.dumps(value), 'other'))
        value['payload']['type'] = 'task_started'
        self.assertFalse(watcher.completed(json.dumps(value), 'owned'))
        for line in ['', '{partial', 'null', '[]', '{"type":"response_item"}']:
            self.assertFalse(watcher.completed(line, 'owned'))


if __name__ == '__main__':
    unittest.main()
