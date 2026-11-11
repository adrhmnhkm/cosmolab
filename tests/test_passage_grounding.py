import unittest
from pathlib import Path
from cosmolab import extract
from cosmolab import retrieval
from cosmolab import config

class TestPassageGrounding(unittest.TestCase):
    def test_extract_pages_from_text_with_markers(self):
        sample_text = (
            "--- [Halaman 1] ---\n"
            "This is the introduction on page one. It lays out the research problem.\n\n"
            "Another paragraph on page one about kalam cosmology.\n\n"
            "--- [Halaman 2] ---\n"
            "This is the methodology on page two. We use empirical analysis here.\n\n"
            "--- [Halaman 3] ---\n"
            "Conclusion on page three with final remarks."
        )
        pages = extract.extract_pages_from_text(sample_text)
        self.assertEqual(len(pages), 3)
        self.assertEqual(pages[0]["page"], 1)
        self.assertEqual(pages[1]["page"], 2)
        self.assertEqual(pages[2]["page"], 3)
        self.assertTrue(any("kalam" in p for p in pages[0]["paragraphs"]))

    def test_extract_pages_from_text_fallback(self):
        sample_legacy_text = (
            "Legacy extracted text without any page markers.\n\n"
            "Second paragraph with some philosophical arguments.\n\n"
            "Third paragraph discussing temporal origins."
        )
        pages = extract.extract_pages_from_text(sample_legacy_text)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["page"], 1)
        self.assertEqual(len(pages[0]["paragraphs"]), 3)

    def test_find_grounded_passages_on_real_pdf(self):
        # Test on one existing paper PDF if present in data/pdf
        test_pdf = config.PDF_DIR / "2012_New_remarks_on_the_Cosmological_Argument.pdf"
        if not test_pdf.exists():
            self.skipTest("Sample PDF not found in data/pdf")

        passages = retrieval.find_grounded_passages(
            "2012_New_remarks_on_the_Cosmological_Argument.pdf",
            "equivocation kalam argument",
            top_k=2
        )
        self.assertTrue(len(passages) > 0)
        top_match = passages[0]
        self.assertIn("page", top_match)
        self.assertIn("page_label", top_match)
        self.assertIn("verbatim", top_match)
        self.assertIn("score", top_match)
        self.assertGreater(top_match["score"], 0)
        # Should be on page 1 where equivocation is explicitly stated in the abstract/intro
        self.assertEqual(top_match["page"], 1)
        self.assertIn("equivocation", top_match["verbatim"].lower())

    def test_get_grounded_passages_for_papers(self):
        papers = [{
            "file": "2012_New_remarks_on_the_Cosmological_Argument.pdf",
            "title": "New remarks on the Cosmological Argument",
            "year": "2012"
        }]
        test_pdf = config.PDF_DIR / papers[0]["file"]
        if not test_pdf.exists():
            self.skipTest("Sample PDF not found in data/pdf")

        results = retrieval.get_grounded_passages_for_papers(papers, "kalam equivocation", passages_per_paper=1)
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["paper_title"], "New remarks on the Cosmological Argument")
        self.assertEqual(results[0]["page"], 1)

if __name__ == "__main__":
    unittest.main()

