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


    def test_resolve_landing_page_meta(self):
        """Test Dublin Core citation_pdf_url extraction from HTML."""
        from unittest.mock import patch, MagicMock
        fake_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="citation_title" content="Test Paper">
            <meta name="citation_pdf_url" content="https://example.com/download/test.pdf">
        </head>
        <body><p>Abstract</p></body>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_resp.text = fake_html
        mock_resp.url = "https://example.com/article/123"

        with patch("requests.get", return_value=mock_resp):
            resolved = harvest._resolve_landing_page_pdf("https://example.com/article/123")
            self.assertEqual(resolved, "https://example.com/download/test.pdf")

    def test_semanticscholar_rate_limit_graceful(self):
        """Test Semantic Scholar skips immediately on 429 without long backoff when no key."""
        from unittest.mock import patch, MagicMock
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        orig_key = config.env_config.get("SEMANTIC_SCHOLAR_API_KEY")
        try:
            config.env_config["SEMANTIC_SCHOLAR_API_KEY"] = ""
            with patch("requests.get", return_value=mock_resp):
                results = harvest._search_semanticscholar("test query", max_results=5)
                self.assertEqual(results, [])
        finally:
            if orig_key:
                config.env_config["SEMANTIC_SCHOLAR_API_KEY"] = orig_key


if __name__ == "__main__":
    unittest.main()
