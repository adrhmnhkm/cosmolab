import unittest
import tempfile
from pathlib import Path
from cosmolab import inspector


class TestDoiInspector(unittest.TestCase):

    def test_normalize_doi(self):
        # Full URL
        url_doi = "https://doi.org/10.1016/j.concog.2020.102980"
        self.assertEqual(inspector.normalize_doi(url_doi), "10.1016/j.concog.2020.102980")

        # Dx URL
        dx_doi = "http://dx.doi.org/10.1007/s00283-022-10224-8"
        self.assertEqual(inspector.normalize_doi(dx_doi), "10.1007/s00283-022-10224-8")

        # Prefix 'doi: '
        pref_doi = "doi: 10.1093/mind/fzv156."
        self.assertEqual(inspector.normalize_doi(pref_doi), "10.1093/mind/fzv156")

        # Raw DOI
        raw = "10.24204/ejpr.v9i2.1938"
        self.assertEqual(inspector.normalize_doi(raw), "10.24204/ejpr.v9i2.1938")

    def test_reconstruct_openalex_abstract(self):
        inv = {
            "The": [0],
            "kalam": [1],
            "cosmological": [2],
            "argument": [3],
            "is": [4],
            "sound.": [5],
        }
        res = inspector._reconstruct_openalex_abstract(inv)
        self.assertEqual(res, "The kalam cosmological argument is sound.")

    def test_clean_abstract(self):
        raw_xml = "<jats:p>This study examines <jats:italic>causality</jats:italic> and consciousness.</jats:p>"
        cleaned = inspector._clean_abstract(raw_xml)
        self.assertEqual(cleaned, "This study examines causality and consciousness.")

    def test_save_inspection(self):
        sample_data = {
            "doi": "10.1016/j.concog.2020.102980",
            "title": "Attachment and autobiographical memory retrieval",
            "authors": ["Yadan Luo", "Chen Liu"],
            "year": "2020",
            "venue": "Consciousness and Cognition",
            "publisher": "Elsevier",
            "citation_count": 4,
            "is_oa": False,
            "url": "https://doi.org/10.1016/j.concog.2020.102980",
            "apa_citation": "Yadan Luo, & Chen Liu (2020). Attachment and autobiographical memory retrieval. *Consciousness and Cognition*.",
            "bibtex": "@article{luo2020, title={Attachment and autobiographical memory retrieval}}",
            "analysis": {
                "one_sentence_takeaway": "Kelekatan memengaruhi pemrosesan strategis memori.",
                "problem_statement": "Mekanisme neurokognitif belum jelas.",
                "methodology": "Eksperimen ERP dan tugas leksikal.",
                "key_findings": ["Pemrosesan strategis berbeda antar kelekatan."],
                "conclusion": "Regulasi strategis mengontrol pemanggilan memori.",
                "research_gaps": ["Pengujian memori valensi emosional spesifik."],
                "highlights": ["Highlights 1", "Highlights 2"]
            }
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_dir = inspector.INSPECTOR_DIR
            try:
                inspector.INSPECTOR_DIR = Path(tmp_dir)
                saved_path = inspector.save_inspection(sample_data)
                self.assertTrue(saved_path.exists())
                self.assertTrue(saved_path.name.endswith(".md"))
                content = saved_path.read_text(encoding="utf-8")
                self.assertIn("Attachment and autobiographical memory retrieval", content)
                self.assertIn("Elsevier", content)
                self.assertIn("Research Highlights", content)
            finally:
                inspector.INSPECTOR_DIR = orig_dir


if __name__ == "__main__":
    unittest.main()

