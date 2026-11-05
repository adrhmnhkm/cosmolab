import unittest
from cosmolab import db
from cosmolab import retrieval

class TestRetrieval(unittest.TestCase):
    def test_weighted_fts5_search(self):
        """Ensure FTS5 search with column weights returns valid results without error."""
        results = db.search("kalam", limit=3)
        self.assertIsInstance(results, list)
        if results:
            self.assertIn("rank", results[0])
            self.assertIn("title", results[0])

    def test_expand_academic_query_heuristic_fallback(self):
        """Test heuristic domain mapping fallback when query expansion is called without network."""
        terms = retrieval.expand_academic_query("apakah alam semesta punya awal mula", client=None)
        self.assertIsInstance(terms, list)
        self.assertTrue(len(terms) > 0)
        # Should contain academic terms mapped from 'alam', 'semesta', 'awal'
        combined = " ".join(terms).lower()
        self.assertTrue("origin" in combined or "beginning" in combined or "kalam" in combined or "cosmolog" in combined)

    def test_hybrid_search_rrf(self):
        """Test that hybrid search combines results and computes RRF scores."""
        results = retrieval.hybrid_search("kalam argument", limit=3, expand_concepts=False)
        self.assertIsInstance(results, list)
        if results:
            self.assertIn("title", results[0])

    def test_rerank_papers_boundary(self):
        """Test that rerank_papers handles small candidate sets safely."""
        candidates = [{"file": "p1.pdf", "title": "Paper 1", "thesis": "Thesis 1"}]
        reranked = retrieval.rerank_papers("query", candidates, top_k=5)
        self.assertEqual(len(reranked), 1)

if __name__ == "__main__":
    unittest.main()

