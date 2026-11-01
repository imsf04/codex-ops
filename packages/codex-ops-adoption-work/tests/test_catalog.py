import copy
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator

import catalog


class CatalogTests(unittest.TestCase):
    def test_thin_listing_has_all_supported_operations_and_no_eager_schemas(self):
        with patch('subprocess.run', side_effect=AssertionError('discovery executes nothing')):
            result = catalog.describe()
        self.assertEqual(len(result['capabilities']), 19)
        self.assertEqual({row['operation'] for row in result['capabilities']}, set(catalog.SCHEMAS) | {'workflows', 'task'})
        self.assertNotIn('argsSchema', str(result))

    def test_every_selected_contract_validates_its_example(self):
        for operation in catalog.SCHEMAS:
            result = catalog.describe(operation)
            schema = result['argsSchema']
            Draft202012Validator.check_schema(schema)
            args = result['example'].get('args')
            if operation in catalog.MUTATIONS:
                args = result['example']['operations'][0]['args']
                self.assertEqual(result['tool'], 'ops_plan')
                self.assertIn('never modify', result['contracts'][0])
            Draft202012Validator(schema).validate(args)
            self.assertFalse(list(Draft202012Validator(schema).iter_errors(args)))

    def test_arguments_are_copied_and_unknown_operations_are_values(self):
        result = catalog.describe('read')
        result['argsSchema']['properties'].clear()
        result['example']['args']['files'].clear()
        self.assertIn('files', catalog.describe('read')['argsSchema']['properties'])
        self.assertTrue(catalog.describe('read')['example']['args']['files'])
        for operation in ('unknown', 'ops_read_files', None, [], 42):
            self.assertEqual(catalog.describe(operation)['error']['code'], 'UNKNOWN_OPERATION')

    def test_schema_rejects_common_wrong_types_and_cross_surface_mutation_args(self):
        cases = [('grep', {'pattern': ['needle']}), ('glob', {'pattern': '*.py'}),
                 ('read', {'files': [{'path': 'x', 'offset': 0}]}), ('search', {'pattern': 'x', 'maxFiles': 9}),
                 ('read_table', {'path': 'x', 'limit': 1001}),
                 ('replace', {'path': 'x', 'pattern': 'a', 'replacement': 'b'}),
                 ('copy', {'path': 'x', 'to': 'y', 'expectedRevision': 'a' * 64}),
                 ('batch', {'requests': [{'operation': 'write', 'args': {'path': 'x', 'content': 'x'}}]})]
        for operation, args in cases:
            self.assertTrue(list(Draft202012Validator(catalog.describe(operation)['argsSchema']).iter_errors(args)))
        self.assertIn('not an atomic snapshot', catalog.describe('search')['contracts'][1])


if __name__ == '__main__':
    unittest.main()
