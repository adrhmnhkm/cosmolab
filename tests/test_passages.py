import unittest
from unittest import mock

from cosmolab import config, passages

PAGES = [
    {"page": 1, "paragraphs": [
        "Abstract. We show that the Kalam argument commits the fallacy of equivocation in its premises.",
        "Short.",
    ]},
    {"page": 2, "paragraphs": [
        "The Aquinas argument does not imply a caused origination of the universe at all.",
        "Quantum correlations can violate the CHSH inequality up to the maximal value of four.",
    ]},
]


class TokenizeTests(unittest.TestCase):
    def test_stems_and_stopwords(self):
        self.assertEqual(passages.tokenize("The causes of violations"), ["caus", "viol"])
        self.assertEqual(passages.tokenize("cause"), passages.tokenize("causes"))

    def test_chunks_skip_short_and_split_long(self):
        long = " ".join(f"Sentence number {i} is here and talks about causality." for i in range(40))
        chunks = passages.chunk_pages([{"page": 3, "paragraphs": ["tiny", long]}])
        self.assertTrue(len(chunks) > 1)
        self.assertTrue(all(c["page"] == 3 and len(c["text"]) <= passages.WINDOW + 80 for c in chunks))


class SearchTests(unittest.TestCase):
    def setUp(self):
        passages.clear_cache()
        self.p = mock.patch("cosmolab.extract.get_paper_pages", return_value=PAGES)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        passages.clear_cache()

    def test_bm25_finds_the_right_page(self):
        with mock.patch.object(config, "EMBED_MODEL", ""):
            hits = passages.search("x.pdf", "CHSH inequality violation", top_k=2)
        self.assertEqual(hits[0]["page"], 2)
        self.assertIn("CHSH", hits[0]["text"])
        self.assertIsNone(hits[0]["dense"])

    def test_extra_terms_count_less_than_query_words(self):
        with mock.patch.object(config, "EMBED_MODEL", ""):
            hits = passages.search("x.pdf", "equivocation", extra_terms="universe origination", top_k=3)
        self.assertEqual(hits[0]["page"], 1)

    def test_dense_rank_is_fused(self):
        # Fake embedding: a passage is "close" to the query only if it mentions Aquinas.
        def fake_embed(texts, kind="passage"):
            return [[1.0, 0.0] if ("Aquinas" in t or kind == "query") else [0.0, 1.0] for t in texts]

        with mock.patch.object(config, "EMBED_MODEL", "fake"), \
                mock.patch.object(passages, "embed", side_effect=fake_embed), \
                mock.patch.object(passages, "_cache_path", return_value=config.ROOT / "embeddings" / "_test.json"):
            hits = passages.search("x.pdf", "siapa yang membahas asal mula alam semesta", top_k=1)
        self.assertEqual(hits[0]["page"], 2)
        self.assertIn("Aquinas", hits[0]["text"])
        self.assertAlmostEqual(hits[0]["dense"], 1.0)
        (config.ROOT / "embeddings" / "_test.json").unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
