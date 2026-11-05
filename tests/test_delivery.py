import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cosmolab import config, deliverables, verify

CORPUS = [
    {"title": "Indeterminism in Kalām and Quantum Mechanics", "year": 2025, "doi": "10.1/abc"},
    {"title": "A Mathematician Reads the Kalam Cosmological Argument", "year": 2022, "doi": ""},
]

ARTICLE = """# Judul Uji

Pembukaan yang mengutip (Malik, 2025) dan Craig (1979), serta (Fiktif, 2011).

## Daftar Rujukan

* Malik, Shoaib Ahmed. (2025). "Indeterminism in Kalām and Quantum Mechanics: A Nuanced Metaphysical Appraisal". *Philosophy East and West*.
* Craig, William Lane. (1979). *The Kalām Cosmological Argument*. London: Macmillan.
* Popescu, Sandu. (1997). "Causality and Nonlocality as Axioms for Quantum Mechanics". *Foundations of Physics*.
"""


def fake_crossref(ref, timeout=15):
    if "Causality and Nonlocality" in ref.title:
        return {"title": ["Causality and nonlocality as axioms for quantum mechanics"], "DOI": "10.1007/x",
                "issued": {"date-parts": [[1994]]}, "author": [{"family": "Popescu"}]}
    if "Kalām Cosmological Argument" in ref.title:
        return {"title": ["The Kalām Cosmological Argument"], "DOI": "10.1007/y",
                "issued": {"date-parts": [[1979]]}, "author": [{"family": "Craig"}]}
    return None


class TestCitationCheck(unittest.TestCase):
    def test_title_similarity_rules(self):
        self.assertEqual(verify.title_similarity(
            "Indeterminism in Kalām and Quantum Mechanics",
            "Indeterminism in Kalam and Quantum Mechanics: A Nuanced Metaphysical Appraisal"), 1.0)
        # A short title inside a different, longer one must not count as a match.
        self.assertLess(verify.title_similarity(
            "The Kalām Cosmological Argument",
            "A Mathematician Reads the Kalam Cosmological Argument"), verify.TITLE_MATCH)

    def test_parse_reference(self):
        ref = verify.parse_reference('Hume, David. (1748/1975). *Enquiries Concerning Human Understanding*. Oxford.')
        self.assertEqual(ref.years, ["1748", "1975"])
        self.assertEqual(ref.title, "Enquiries Concerning Human Understanding")
        self.assertIn("Hume", ref.authors)

    def test_verify_flags_wrong_year_and_missing_reference(self):
        with mock.patch.object(verify, "lookup_crossref", side_effect=fake_crossref):
            report = verify.verify_markdown(ARTICLE, source="uji.md", online=True, corpus=CORPUS)
        status = {r.title.split(":")[0]: r.status for r in report.references}
        self.assertEqual(status["Indeterminism in Kalām and Quantum Mechanics"], verify.OK_CORPUS)
        self.assertEqual(status["The Kalām Cosmological Argument"], verify.OK_CROSSREF)
        self.assertEqual(status["Causality and Nonlocality as Axioms for Quantum Mechanics"], verify.YEAR_MISMATCH)
        cites = {c.name: c.status for c in report.citations}
        self.assertEqual(cites["Malik"], verify.CITE_OK)
        self.assertEqual(cites["Craig"], verify.CITE_OK)
        self.assertEqual(cites["Fiktif"], verify.CITE_NO_REFERENCE)
        self.assertFalse(report.ok)

    def test_offline_marks_unknown_as_not_checked(self):
        report = verify.verify_markdown(ARTICLE, online=False, corpus=CORPUS)
        self.assertIn(verify.SKIPPED, {r.status for r in report.references})


class TestDelivery(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._root = config.ROOT
        config._set_root(Path(self._tmp.name))
        self.src = Path(self._tmp.name) / "artikel.md"
        self.src.write_text(ARTICLE, encoding="utf-8")

    def tearDown(self):
        config._set_root(self._root)
        self._tmp.cleanup()

    def test_blocks_until_reviewed(self):
        with mock.patch.object(verify, "_load_corpus", return_value=CORPUS), \
             mock.patch.object(verify, "lookup_crossref", side_effect=fake_crossref):
            with self.assertRaises(deliverables.DeliveryBlocked):
                deliverables.deliver(self.src, reviewer="Dr. Uji")
            with self.assertRaises(ValueError):
                deliverables.deliver(self.src, reviewer="  ", allow_unverified=True)
            result = deliverables.deliver(self.src, reviewer="Dr. Uji", allow_unverified=True)

        names = sorted(f.suffix for f in result["files"])
        self.assertEqual(names, [".docx", ".pdf"])
        for f in result["files"]:
            self.assertTrue(f.exists() and f.stat().st_size > 0)
            self.assertEqual(f.parent, Path(self._tmp.name) / "deliverables")
        self.assertTrue(result["qa_report"].exists())

        import docx
        import pymupdf
        text = "\n".join(p.text for p in docx.Document(str(result["files"][0])).paragraphs)
        self.assertIn("Judul Uji", text)
        self.assertIn("Dr. Uji", text)
        self.assertIn("diperiksa manual", text)  # note must not claim full verification
        pdf = pymupdf.open(str(result["files"][1]))
        self.assertGreaterEqual(pdf.page_count, 2)
        self.assertIn("Halaman 1", pdf[1].get_text())


if __name__ == "__main__":
    unittest.main()
