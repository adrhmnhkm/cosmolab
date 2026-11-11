import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from cosmolab import dois


class IdTests(unittest.TestCase):
    def test_clean_doi(self):
        self.assertEqual(dois.clean_doi("https://doi.org/10.1007/s11153-012-9337-6"), "10.1007/s11153-012-9337-6")
        self.assertEqual(dois.clean_doi("doi: 10.22331/q-2020-03-02-240"), "10.22331/q-2020-03-02-240")
        self.assertEqual(dois.clean_doi("N/A"), "")
        self.assertEqual(dois.clean_doi(None), "")

    def test_arxiv_ids_new_and_old_style(self):
        self.assertEqual(dois.arxiv_id("https://arxiv.org/pdf/2207.06165v1"), "2207.06165")
        self.assertEqual(dois.arxiv_id("http://arxiv.org/abs/1412.5701v1"), "1412.5701")
        self.assertEqual(dois.arxiv_id("https://arxiv.org/pdf/quant-ph/0701019v1"), "quant-ph/0701019")
        self.assertEqual(dois.arxiv_id("2403.09368"), "2403.09368")
        self.assertEqual(dois.arxiv_id("https://ipssj.com/index.php/ojs/article/download/1428/1347"), "")

    def test_arxiv_doi_and_journal_doi(self):
        self.assertEqual(dois.arxiv_doi("2512.10504"), "10.48550/arXiv.2512.10504")
        entry = ET.fromstring(
            '<entry xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">'
            "<arxiv:doi>10.1063/5.0298701</arxiv:doi></entry>")
        self.assertEqual(dois.arxiv_journal_doi(entry), "10.1063/5.0298701")
        self.assertEqual(dois.arxiv_journal_doi(None), "")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_manual_entry_is_not_overwritten(self):
        dois.save_entry("a.pdf", "10.1/manual", dois.MANUAL, root=self.root)
        self.assertFalse(dois.save_entry("a.pdf", "10.1/lookup", "crossref", root=self.root))
        self.assertEqual(dois.load(self.root)["a.pdf"]["doi"], "10.1/manual")

    def test_pick_order(self):
        store = {"a.pdf": {"doi": "10.1/manual", "source": "manual"}, "b.pdf": {"doi": "10.1/look", "source": "arxiv"}}
        self.assertEqual(dois.pick("a.pdf", "10.1/meta", store), ("10.1/manual", "manual"))
        self.assertEqual(dois.pick("b.pdf", "https://doi.org/10.1/meta", store), ("10.1/meta", "metadata"))
        self.assertEqual(dois.pick("b.pdf", "", store), ("10.1/look", "arxiv"))
        self.assertEqual(dois.pick("c.pdf", None, store), ("", ""))


class LookupTests(unittest.TestCase):
    def _crossref(self, items):
        resp = mock.Mock()
        resp.json.return_value = {"message": {"items": items}}
        return resp

    def test_title_match_needs_same_year(self):
        item = {"DOI": "10.5/x", "title": ["Exact Same Title Here"], "issued": {"date-parts": [[2024]]}}
        with mock.patch.object(dois, "_get", return_value=self._crossref([item])):
            self.assertEqual(dois.by_title("Exact Same Title Here", "2024")[:2], ("10.5/x", "crossref"))
            doi, src, cands = dois.by_title("Exact Same Title Here", "2019")
            self.assertEqual((doi, src), ("", ""))
            self.assertEqual(cands[0]["doi"], "10.5/x")

    def test_arxiv_falls_back_to_arxiv_doi(self):
        empty = mock.Mock(content=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry></entry></feed>')
        with mock.patch.object(dois, "_get", return_value=empty):
            self.assertEqual(dois.by_arxiv("2110.06500"), ("10.48550/arXiv.2110.06500", "arxiv"))
            doi, src, _ = dois.resolve({"source": "arxiv", "url": "https://arxiv.org/pdf/quant-ph/9709026v2"})
            self.assertEqual((doi, src), ("10.48550/arXiv.quant-ph/9709026", "arxiv"))


if __name__ == "__main__":
    unittest.main()
