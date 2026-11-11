import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cosmolab import config, llmcache, passages


class LlmCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(config, "ROOT", Path(self.tmp.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_put_get_roundtrip(self):
        k = llmcache.key("rerank", "m", ["a", "b"])
        self.assertIsNone(llmcache.get(k))
        llmcache.put(k, [1, 0])
        self.assertEqual(llmcache.get(k), [1, 0])

    def test_rerank_second_call_uses_cache(self):
        hits = [{"text": "a", "bm25": 1.0, "dense": None, "page": 1, "score": 100},
                {"text": "b", "bm25": 0.9, "dense": None, "page": 2, "score": 90}]
        calls = []

        def fake(q, texts, model):
            calls.append(1)
            return [1, 0]

        with mock.patch.object(passages, "_llm_rerank", fake):
            first = passages.rerank("q", [dict(h) for h in hits])
            second = passages.rerank("q", [dict(h) for h in hits])
        self.assertEqual(len(calls), 1)
        self.assertEqual([h["text"] for h in first], ["b", "a"])
        self.assertEqual([h["text"] for h in second], ["b", "a"])

    def test_confident_skips_rerank(self):
        clear = [{"text": "a", "bm25": 5.0, "dense": 0.9}, {"text": "b", "bm25": 2.0, "dense": 0.5}]
        close = [{"text": "a", "bm25": 5.0, "dense": 0.9}, {"text": "b", "bm25": 4.5, "dense": 0.5}]
        split = [{"text": "a", "bm25": 5.0, "dense": 0.5}, {"text": "b", "bm25": 2.0, "dense": 0.9}]
        self.assertTrue(passages.confident(clear))
        self.assertFalse(passages.confident(close))
        self.assertFalse(passages.confident(split))
        with mock.patch.object(passages, "_llm_rerank", side_effect=AssertionError("no call")):
            self.assertEqual(passages.rerank("q", clear), clear)


if __name__ == "__main__":
    unittest.main()
