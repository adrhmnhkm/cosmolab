import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cosmolab import config, coverage, review, similarity

from test_similarity import COPY, OTHER, SOURCE, SOURCE_TEXT

REFS = [
    # in the collection already (same title as SOURCE)
    {"raw": "Rahman, A. (2019). Literasi keuangan syariah dan UMKM. Jurnal Ekonomi Islam, 4(2), 10-20.",
     "title": "Literasi keuangan syariah dan UMKM", "authors": "Rahman, A.", "years": ["2019"], "doi": "",
     "status": "ok_crossref"},
    # open copy found by DOI
    {"raw": "Lubis, C. (2020). Pembiayaan bagi hasil. Jurnal Keuangan, 2(1), 1-9. https://doi.org/10.9/lubis",
     "title": "Pembiayaan bagi hasil", "authors": "Lubis, C.", "years": ["2020"], "doi": "10.9/lubis",
     "status": "ok_crossref"},
    # closed, but OpenAlex has its abstract
    {"raw": "Nasution, D. (2018). Minat UMKM. Jurnal Bisnis, 3(1), 5-9.", "title": "Minat UMKM",
     "authors": "Nasution, D.", "years": ["2018"], "doi": "10.9/nasution", "status": "ok_crossref"},
    # a book
    {"raw": "Sugiyono. (2017). Metode Penelitian Kuantitatif. Bandung: Alfabeta.",
     "title": "Metode Penelitian Kuantitatif", "authors": "Sugiyono", "years": ["2017"], "doi": "",
     "status": "not_found"},
]


class TestHelpers(unittest.TestCase):
    def test_guess_kind(self):
        self.assertEqual(coverage.guess_kind(REFS[0]["raw"]), "jurnal")
        self.assertEqual(coverage.guess_kind(REFS[3]["raw"]), "buku")
        self.assertEqual(coverage.guess_kind("Undang-Undang Nomor 21 Tahun 2008 tentang Perbankan Syariah."), "peraturan")
        self.assertEqual(coverage.guess_kind("Hakim, A. (2020). Judul. Skripsi, Universitas X."), "skripsi")
        self.assertEqual(coverage.guess_kind("OJK. (2022). Statistik. https://ojk.go.id/statistik"), "situs")

    def test_entry_url(self):
        self.assertEqual(coverage.entry_url("Judul. Jurnal X, https://ejournal.ac.id/index.php/jx/article/view/12/34."),
                         "https://ejournal.ac.id/index.php/jx/article/download/12/34")
        self.assertEqual(coverage.entry_url("https://doi.org/10.1/x"), "")
        self.assertEqual(coverage.entry_url("tanpa link"), "")


class TestFill(unittest.TestCase):
    def setUp(self):
        self._old = config.ROOT
        self._tmp = tempfile.TemporaryDirectory()
        config._set_root(Path(self._tmp.name) / "data")
        config.ensure_dirs()
        self.corpus = [SOURCE, OTHER]
        self._patches = [
            mock.patch.object(similarity, "corpus_sources", lambda: self.corpus),
            mock.patch("cosmolab.db.sync_one", lambda f: None),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        config._set_root(self._old)
        self._tmp.cleanup()

    def _report(self):
        draft = "\n\n".join(["# Bab 2", f"Menurut pengamatan awal, {COPY}. Penulis mewawancarai dua belas pedagang pasar.",
                             "DAFTAR PUSTAKA"] + [r["raw"] for r in REFS])
        r = review.review_text(draft, title="Draf", online=False, feedback=False)
        r["citations"]["references"] = [dict(x) for x in REFS]
        return r

    def test_fill_records_coverage_and_skips_tried(self):
        calls = []

        def by_doi(ref):
            calls.append(ref["raw"][:6])
            if ref.get("doi") == "10.9/lubis":
                self.corpus = self.corpus + [{**OTHER, "title": "Pembiayaan bagi hasil", "doi": "10.9/lubis",
                                              "file": "lubis.pdf", "text": SOURCE_TEXT}]
                return {"ok": True, "file": "lubis.pdf"}
            return None

        r = self._report()
        events = []
        coverage.fill(r, steps=(by_doi,), progress_cb=lambda kind, msg, data=None: events.append(kind))
        status = {it["i"]: it["status"] for it in r["coverage"]["items"]}
        self.assertEqual(status, {0: coverage.IN_COLLECTION, 1: coverage.DOWNLOADED,
                                  2: coverage.MISSING, 3: coverage.MISSING})
        self.assertEqual(sorted(calls), ["Lubis,", "Nasuti", "Sugiyo"])
        self.assertIn("item", events)

        # Abstract used by the similarity check upgrades the closed article.
        with mock.patch.object(similarity, "_cached_abstract", lambda doi: "abstrak nasution" if "nasution" in doi else ""):
            review.run_similarity(r)
        status = {it["i"]: it["status"] for it in r["coverage"]["items"]}
        self.assertEqual(status[2], coverage.ABSTRACT)
        s = coverage.summary(r)
        self.assertEqual((s["full_text"], s["abstract"], s["missing"]), (2, 1, 1))
        self.assertEqual(s["missing_by_kind"], {"buku": 1})
        self.assertIn("1 tidak bisa dibandingkan (1 buku)", coverage.summary_text(s))

        # A second fill does not search again for what was already tried.
        calls.clear()
        coverage.fill(r, steps=(by_doi,))
        self.assertEqual(calls, [])

        internal = review.report_markdown(r, final=False)
        self.assertIn("Sumber yang perlu diminta ke mahasiswa", internal)
        self.assertIn("[Buku] Sugiyono", internal)
        final = review.report_markdown(r, final=True)
        self.assertIn("tidak bisa dibandingkan", final)
        self.assertNotIn("perlu diminta", final)

    def test_upload_from_student(self):
        r = self._report()
        coverage.fill(r, steps=())
        with mock.patch("cosmolab.extract._pdf_to_text", lambda p: "teks buku sugiyono"):
            coverage.add_upload(r, 3, b"%PDF-1.4 fake", "sugiyono_bab3.pdf")
        item = [it for it in r["coverage"]["items"] if it["i"] == 3][0]
        self.assertEqual(item["status"], coverage.UPLOADED)
        meta = (config.ROOT / "metadata.jsonl").read_text(encoding="utf-8")
        self.assertIn('"title": "Metode Penelitian Kuantitatif"', meta)
        self.assertIn('"year": "2017"', meta)
        self.assertIn('"authors": ["Sugiyono"]', meta)


if __name__ == "__main__":
    unittest.main()
