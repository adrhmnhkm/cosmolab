import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cosmolab import authors, citations


class NameTests(unittest.TestCase):
    def test_clean_names_drops_organisations_and_duplicates(self):
        names = authors.clean_names(["  Ali  Akbar ", "ali akbar", "International Islamic University Malaysia (IIUM)", "", "Budi"])
        self.assertEqual(names, ["Ali Akbar", "Budi"])

    def test_source_formats(self):
        self.assertEqual(authors.from_crossref([{"given": "Ada", "family": "Lovelace"}, {"name": "Grace Hopper"}]),
                         ["Ada Lovelace", "Grace Hopper"])
        work = {"authorships": [{"author": {"display_name": "Alan Turing"}}]}
        self.assertEqual(authors.from_openalex(work), ["Alan Turing"])
        self.assertEqual(authors.from_named([{"name": "Emmy Noether"}]), ["Emmy Noether"])

    def test_display_and_in_text(self):
        self.assertEqual(authors.display(["A B"]), "A B")
        self.assertEqual(authors.display(["A B", "C D"]), "A B & C D")
        self.assertEqual(authors.display(["A", "B", "C"]), "A, B & C")
        self.assertEqual(authors.display(["A", "B", "C", "D"]), "A et al.")
        self.assertEqual(authors.in_text(["Siti Aminah", "Budi Santoso"]), "Aminah & Santoso")
        self.assertEqual(authors.in_text(["Siti Aminah", "Budi Santoso", "C D"]), "Aminah et al.")

    def test_as_list_reads_json_and_text(self):
        self.assertEqual(authors.as_list('["A", "B"]'), ["A", "B"])
        self.assertEqual(authors.as_list("Solo Author"), ["Solo Author"])
        self.assertEqual(authors.as_list(None), [])

    def test_ai_names_must_appear_in_page(self):
        page = "Pengaruh Zakat\nPutri Nabillah Julia, Rayyan Firdaus\nUniversitas Malikussaleh"
        self.assertTrue(authors._appears_in("Putri Nabillah Julia", page))
        self.assertFalse(authors._appears_in("John Invented", page))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_manual_entry_is_not_overwritten(self):
        authors.save_entry("a.pdf", ["Manual Name"], authors.MANUAL, root=self.root)
        self.assertFalse(authors.save_entry("a.pdf", ["Looked Up"], "doi", root=self.root))
        self.assertEqual(authors.load(self.root)["a.pdf"]["authors"], ["Manual Name"])

    def test_pick_order(self):
        store = {"a.pdf": {"authors": ["Manual"], "source": "manual"},
                 "b.pdf": {"authors": ["Looked Up"], "source": "doi"}}
        self.assertEqual(authors.pick("a.pdf", ["From Meta"], store), (["Manual"], "manual"))
        self.assertEqual(authors.pick("b.pdf", ["From Meta"], store), (["From Meta"], "metadata"))
        self.assertEqual(authors.pick("b.pdf", None, store), (["Looked Up"], "doi"))
        self.assertEqual(authors.pick("c.pdf", None, store), ([], ""))

    def test_resolve_falls_through_sources(self):
        rec = {"doi": "", "title": "Some Title", "file": "x.pdf"}
        with mock.patch.object(authors, "by_doi", return_value=[]), \
             mock.patch.object(authors, "by_arxiv", return_value=[]), \
             mock.patch.object(authors, "by_title", return_value=([], "")), \
             mock.patch.object(authors, "by_pdf_ai", return_value=["Read From Pdf"]) as ai:
            self.assertEqual(authors.resolve(rec), (["Read From Pdf"], "pdf_ai"))
            self.assertEqual(authors.resolve(rec, use_ai=False), ([], ""))
            ai.assert_called_once()


class CitationTests(unittest.TestCase):
    def test_citations_use_stored_authors(self):
        paper = {"authors": json.dumps(["Siti Aminah", "Budi Santoso"]), "year": "2024", "title": "Judul"}
        self.assertEqual(citations._infer_author(paper), "Siti Aminah & Budi Santoso")
        self.assertEqual(citations.format_in_text_apa(paper), "(Aminah & Santoso, 2024)")

    def test_unknown_author_falls_back(self):
        self.assertEqual(citations._infer_author({"title": "Nothing known"}), "Anonim")


if __name__ == "__main__":
    unittest.main()
