import os
import sys
import unittest

from google.api_core import exceptions as core_exceptions
from google.api_core import gapic_v1

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from firestore_resilience import FIRESTORE_STREAM_RETRY, stream_collection_resilient


class _FakeCollection:
    def __init__(self):
        self.kwargs = None

    def stream(self, **kwargs):
        self.kwargs = kwargs
        return iter(("doc-1", "doc-2"))


class TestFirestoreStreamResilience(unittest.TestCase):
    def test_passes_concrete_retry_instead_of_gapic_default(self):
        collection = _FakeCollection()
        self.assertEqual(list(stream_collection_resilient(collection, timeout=45)), ["doc-1", "doc-2"])
        self.assertIs(collection.kwargs["retry"], FIRESTORE_STREAM_RETRY)
        self.assertIsNot(collection.kwargs["retry"], gapic_v1.method.DEFAULT)
        self.assertEqual(collection.kwargs["timeout"], 45)

    def test_retries_transient_firestore_errors_only(self):
        predicate = FIRESTORE_STREAM_RETRY._predicate
        self.assertTrue(predicate(core_exceptions.ServiceUnavailable("temporário")))
        self.assertTrue(predicate(core_exceptions.DeadlineExceeded("temporário")))
        self.assertFalse(predicate(core_exceptions.InvalidArgument("definitivo")))


if __name__ == "__main__":
    unittest.main()
