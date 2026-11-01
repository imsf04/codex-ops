import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cache_reader
import session_scope as scope
from store import Store, ReferenceUnavailable

A = '01a18391-1809-7601-96cc-09b2c96329c1'
B = '01a18391-1809-7601-96cc-09b2c96329c2'


def owner(thread=A, mode='workspace-write'):
    return scope.from_meta({'threadId': thread, 'x-codex-turn-metadata': {
        'thread_id': thread, 'sandbox_mode': mode}}, '100')


class OwnershipTests(unittest.TestCase):
    def test_native_metadata_and_permission_change_bind_references(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(temporary)
            try:
                with scope.bind(owner()):
                    ref = store.capture({'body': 'x' * 9000}, force=True)['ref']
                    self.assertEqual(store.get(ref)['body'], 'x' * 9000)
                for caller in (None, owner(B), owner(mode='read-only')):
                    with scope.bind(caller):
                        self.assertEqual(store.result(ref)['error']['code'], 'REFERENCE_UNAVAILABLE')
                        self.assertEqual(store.result(ref, action='release')['error']['code'], 'REFERENCE_UNAVAILABLE')
                with scope.bind(owner()):
                    self.assertTrue(store.result(ref, action='release')['released'])
            finally:
                store.close()

    def test_dedup_never_shares_between_chats_and_runtime_refs_remain_runtime_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(temporary)
            try:
                with scope.bind(owner()):
                    first = store.capture('same', force=True)['ref']
                    self.assertEqual(first, store.capture('same', force=True)['ref'])
                with scope.bind(owner(B)):
                    self.assertNotEqual(first, store.capture('same', force=True)['ref'])
                with scope.bind(scope.for_runtime(100)):
                    runtime_ref = store.capture('runtime', force=True)['ref']
                with scope.bind(owner(B)):
                    self.assertEqual(store.get(runtime_ref), 'runtime')
                with scope.bind(scope.for_runtime(200)):
                    with self.assertRaises(ReferenceUnavailable):
                        store.get(runtime_ref)
            finally:
                store.close()

    def test_legacy_refs_expire_normally_and_binding_restores_on_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(temporary)
            ref = store.capture('legacy', force=True)['ref']
            with scope.bind(owner(B)):
                self.assertEqual(store.get(ref), 'legacy')
            store.close()
        with self.assertRaises(ValueError):
            with scope.bind(owner()):
                raise ValueError('test')
        self.assertIsNone(scope.CURRENT.get())
        self.assertEqual(scope.identity(owner()), 'chat:' + A)
        self.assertEqual(scope.identity(scope.for_runtime(100)), 'runtime:100')

    def test_native_plan_read_requires_matching_native_thread(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(temporary)
            with scope.bind(owner()):
                ref = store.capture({'plan': 'unchanged'}, force=True)['ref']
            store.close()
            with patch.dict(os.environ, {'CODEX_THREAD_ID': A}):
                self.assertEqual(cache_reader.load(ref, temporary), {'plan': 'unchanged'})
            for thread in (B, '', 'malformed'):
                with patch.dict(os.environ, {'CODEX_THREAD_ID': thread}):
                    with self.assertRaisesRegex(ValueError, 'another native session'):
                        cache_reader.load(ref, temporary)

    def test_missing_or_conflicting_metadata_never_claims_chat_ownership(self):
        for meta in (None, {}, {'threadId': A, 'x-codex-turn-metadata': []},
                     {'threadId': A, 'x-codex-turn-metadata': {'thread_id': B}}):
            self.assertIsNone(scope.from_meta(meta)['session'])
        self.assertIsNone(scope.policy({}))
        self.assertIsNone(scope.policy({'x-codex-turn-metadata': []}))
        self.assertEqual(scope.from_meta({'threadId': A})['session'], 'chat:' + A)
        with scope.bind(scope.for_runtime(100)):
            bound = scope.encode_scope('test')
        self.assertFalse(scope.permitted(bound, {}))
        self.assertFalse(scope.permitted(scope.PREFIX + json.dumps({'owner': {}}), owner()))


if __name__ == '__main__':
    unittest.main()
