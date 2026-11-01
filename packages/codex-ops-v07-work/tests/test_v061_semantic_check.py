import copy
import unittest
from v061_semantic_check import canonical, outcome


class SemanticChecks(unittest.TestCase):
    def test_authority_accepts_meaning_but_rejects_reversed_authority(self):
        for value in ('Suspension overrides ownership', 'suspension overrides owner status', 'suspended', False):
            self.assertEqual(canonical('code_location_authority', 'C:/fixture', {'override': value}), {'override': 'suspended'})
        for value in (True, 'Ownership overrides suspension', 'owner status overrides suspension', 'not suspended', None, 'owner'):
            self.assertNotEqual(canonical('code_location_authority', 'C:/fixture', {'override': value}), {'override': 'suspended'})

    def test_compiler_preserves_required_facts_and_rejects_reversed_types(self):
        actual = {'root_cause': 'A string is assigned to the numeric User.age property (TS2322).',
                  'observed': 'source.age is a string ("42").', 'expected': 'User.age must be a number.',
                  'file': 'src/user.ts', 'line': 8, 'evidence_line': 66}
        wanted = {'root_cause': 'TS2322', 'observed': 'string', 'expected': 'number',
                  'file': 'src/user.ts', 'line': 8, 'evidence_line': 66}
        self.assertEqual(canonical('log_diagnosis_compiler', 'C:/fixture', actual), wanted)
        descriptive = {**actual, 'root_cause': 'A string value is assigned to User.age, which is declared as a number.'}
        self.assertEqual(canonical('log_diagnosis_compiler', 'C:/fixture', descriptive), wanted)
        for key, bad in [('observed', 'number'), ('expected', 'string'), ('line', 7),
                         ('root_cause', 'TS9999'), ('root_cause', 'TASK_FAILED'),
                         ('root_cause', 'A number value is assigned to User.age, which is declared as a string.'),
                         ('observed', 'source.age is not a string ("42").'),
                         ('expected', 'User.age must not be a number.'), ('file', 'src/other.ts')]:
            self.assertNotEqual(canonical('log_diagnosis_compiler', 'C:/fixture', {**actual, key: bad}), wanted)

    def test_input_mutations_and_extra_fields_never_turn_into_success(self):
        strict = {'passed': False, 'failures': [{'reason': 'input changed or disappeared'}]}
        row = {'task': 'code_location_authority', 'workspace': 'C:/fixture', 'outcome': strict}
        saved = copy.deepcopy(row)
        self.assertFalse(outcome(row, {'answer': {'override': 'suspended'}})['passed'])
        self.assertEqual(row, saved)
        row['outcome'] = {'passed': False, 'failures': [{'reason': 'answer differs from independent oracle',
                         'observed': {'override': False, 'extra': 1}}]}
        self.assertFalse(outcome(row, {'answer': {'override': 'suspended'}})['passed'])


if __name__ == '__main__':
    unittest.main()
