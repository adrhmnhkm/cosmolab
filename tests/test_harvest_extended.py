import unittest
from cosmolab import harvest, config


class TestHarvestExtended(unittest.TestCase):

    def test_search_crossref(self):
        """Test querying Crossref API for philosophy / kalam works."""
        works = harvest._search_crossref("kalam cosmological argument", max_results=2)
        self.assertIsInstance(works, list)
        if works:
            w = works[0]
            self.assertIn("title", w)
            self.assertIn("doi", w)
            self.assertEqual(w["source"], "crossref")

    def test_search_core_without_key(self):
        """Test CORE API search without key returns empty list gracefully."""
        orig_key = config.CORE_API_KEY
        try:
            config.CORE_API_KEY = ""
            works = harvest._search_core("kalam cosmological", max_results=2)
            self.assertEqual(works, [])
        finally:
            config.CORE_API_KEY = orig_key

    def test_federated_search_integration(self):
        """Test federated search incorporates all active sources."""
        works = harvest._search("contingency argument leibniz", max_results=4)
        self.assertIsInstance(works, list)
        self.assertGreater(len(works), 0)


if __name__ == "__main__":
    unittest.main()
