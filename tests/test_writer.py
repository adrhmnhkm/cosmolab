import unittest
from pathlib import Path
from cosmolab import writer


class TestWriterModule(unittest.TestCase):

    def test_article_styles_configuration(self):
        """Test that available article styles are properly configured."""
        self.assertIn("essay", writer.ARTICLE_STYLES)
        self.assertIn("journal_review", writer.ARTICLE_STYLES)
        self.assertIn("monograph", writer.ARTICLE_STYLES)

        for s_id, s_info in writer.ARTICLE_STYLES.items():
            self.assertTrue(len(s_info["name"]) > 0)
            self.assertTrue(len(s_info["prompt_instructions"]) > 50)

    def test_estimate_reading_time(self):
        """Test calculation of reading time."""
        short_text = "word " * 150
        medium_text = "word " * 600
        self.assertEqual(writer._estimate_reading_time(short_text), 1)
        self.assertEqual(writer._estimate_reading_time(medium_text), 3)

    def test_format_article_html(self):
        """Test generating standalone HTML with KaTeX and print stylesheet."""
        mock_article = {
            "title": "Teka-teki Sebab Akibat",
            "style_name": "Esai Intelektual Populer",
            "reading_time_min": 7,
            "created_at": "2026-10-26 22:30",
            "content_md": "# Teka-teki Sebab Akibat\n\nApakah $E=mc^2$ membuktikan keabadian alam? Al-Ghazali membantahnya.",
        }

        html = writer.format_article_html(mock_article)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<title>Teka-teki Sebab Akibat — CosmoLab University</title>", html)
        self.assertIn("katex", html.lower())
        self.assertIn("window.print()", html)
        self.assertIn("Esai Intelektual Populer", html)

    def test_save_article(self):
        """Test saving article to disk and verify files exist."""
        mock_article = {
            "title": "Uji Coba Simpan File",
            "style_name": "Esai Ilmiah",
            "reading_time_min": 2,
            "created_at": "2026-10-26",
            "content_md": "# Uji Coba\n\nIni adalah pengujian penyimpanan artikel.",
        }

        paths = writer.save_article(mock_article)
        self.assertTrue(paths["md_path"].exists())
        self.assertTrue(paths["html_path"].exists())

        # Cleanup
        paths["md_path"].unlink(missing_ok=True)
        paths["html_path"].unlink(missing_ok=True)
        paths["obsidian_path"].unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
