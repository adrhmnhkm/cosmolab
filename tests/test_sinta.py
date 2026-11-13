import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cosmolab import config, harvest, sinta


class TestIssn(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(sinta.normalize_issn("2087 1236"), "2087-1236")
        self.assertEqual(sinta.normalize_issn("0378-5955"), "0378-5955")
        self.assertEqual(sinta.normalize_issn("2434-561x"), "2434-561X")  # X check digit
        self.assertEqual(sinta.normalize_issn("2087-1237"), "")  # wrong check digit
        self.assertEqual(sinta.normalize_issn("123"), "")
        self.assertEqual(sinta.normalize_issn(None), "")

    def test_parse_rank(self):
        for raw in ("2", "S2", "SINTA 2", "Sinta-2", " s 2 "):
            self.assertEqual(sinta.parse_rank(raw), 2, raw)
        for raw in ("7", "", "Peringkat", "12"):
            self.assertIsNone(sinta.parse_rank(raw), raw)


class TestSintaList(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._old_root = config.ROOT
        config._set_root(tmp / "data")
        config.ensure_dirs()
        self._patch = mock.patch.object(sinta, "list_path", lambda: tmp / "shared" / "sinta.json")
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        config._set_root(self._old_root)
        self._tmp.cleanup()

    def test_add_update_remove(self):
        self.assertEqual(sinta.add("Jurnal A", "2087-1236, 0378 5955", "S3")["status"], "added")
        # Same journal through its other ISSN: updated, not duplicated.
        self.assertEqual(sinta.add("", ["0378-5955"], 2)["status"], "updated")
        entries = sinta.load()
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0]["name"], entries[0]["rank"]), ("Jurnal A", 2))
        self.assertEqual(sinta.rank_for(["20871236"])["rank"], 2)
        with self.assertRaises(ValueError):
            sinta.add("X", "1234-5678", 2)  # bad checksum
        with self.assertRaises(ValueError):
            sinta.add("X", "2087-1236", 9)
        self.assertTrue(sinta.remove("0378-5955"))
        self.assertEqual(sinta.load(), [])

    def test_import_csv(self):
        csv_path = Path(self._tmp.name) / "s.csv"
        csv_path.write_text(
            "Nama Jurnal;P-ISSN;E-ISSN;Akreditasi\n"
            "Jurnal Ekonomi;2087-1236;0378-5955;Sinta 2\n"
            "Jurnal Rusak;1234-5678;;S3\n"
            "Jurnal Hukum;2434-561X;;4\n",
            encoding="utf-8-sig",
        )
        res = sinta.import_csv(csv_path)
        self.assertEqual((res["added"], res["updated"], res["skipped"]), (2, 0, [3]))
        self.assertEqual(sinta.rank_for(["0378-5955"])["name"], "Jurnal Ekonomi")
        res = sinta.import_csv(csv_path)
        self.assertEqual((res["added"], res["updated"]), (0, 2))

        bad = Path(self._tmp.name) / "bad.csv"
        bad.write_text("nama,kota\nA,B\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            sinta.import_csv(bad)

    def test_papers_get_ranks(self):
        sinta.add("Jurnal A", "2087-1236", 1)
        sinta.add("Jurnal B", "0378-5955", 5)
        meta = [
            {"file": "a.pdf", "doi": "10.1/a", "journal": "Jurnal A", "issn": ["2087-1236"]},
            {"file": "b.pdf", "doi": "10.1/b"},
            {"file": "c.pdf", "doi": "10.1/c"},
            {"file": "d.pdf"},
        ]
        config.META_FILE.write_text("\n".join(json.dumps(m) for m in meta), encoding="utf-8")

        asked = []

        def fetch(doi):
            asked.append(doi)
            return {"journal": "Jurnal B", "issn": ["0378-5955"]} if doi == "10.1/b" else None

        self.assertEqual(sinta.fill_journals(fetch=fetch), {"checked": 2, "found": 1})
        self.assertEqual(sorted(asked), ["10.1/b", "10.1/c"])
        # Misses are remembered, so a second run asks nothing.
        self.assertEqual(sinta.fill_journals(fetch=fetch), {"checked": 0, "found": 0})

        ranks = sinta.ranks_by_file()
        self.assertEqual({f: e["rank"] for f, e in ranks.items()}, {"a.pdf": 1, "b.pdf": 5})
        self.assertEqual(sinta.label(ranks["a.pdf"]), "SINTA 1")


class TestHarvestIndonesia(unittest.TestCase):
    def test_journal_info(self):
        oa = {"primary_location": {"source": {"display_name": "Jurnal A", "issn_l": "2087-1236",
                                              "issn": ["0378-5955", "2087-1236"]}}}
        self.assertEqual(harvest.journal_info(oa), ("Jurnal A", ["0378-5955", "2087-1236"]))
        self.assertEqual(harvest.journal_info({"journal": "B", "issn": ["x", ""]}), ("B", ["x"]))
        self.assertEqual(harvest.journal_info({}), ("", []))

    def test_indonesia_search_uses_openalex_filters(self):
        calls = []

        def fake_openalex(query, n, extra=""):
            calls.append(extra)
            return [{"id": f"W{len(calls)}", "title": f"Literasi keuangan syariah {extra}", "abstract": ""}]

        with mock.patch.object(harvest, "_search_openalex", fake_openalex), \
                mock.patch.object(harvest, "_search_crossref", side_effect=AssertionError("not used")):
            works = harvest._search("literasi keuangan syariah", 5, indonesia=True)
        self.assertEqual(sorted(calls), sorted(harvest.INDONESIA_FILTERS))
        self.assertEqual(len(works), 2)


if __name__ == "__main__":
    unittest.main()
