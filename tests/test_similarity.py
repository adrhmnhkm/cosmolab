import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cosmolab import config, review, similarity

SOURCE_TEXT = (
    "Abstrak. Literasi keuangan syariah memiliki pengaruh positif dan signifikan terhadap keputusan pelaku usaha mikro "
    "dalam memilih produk pembiayaan berbasis bagi hasil di wilayah perkotaan Jawa Barat. Penelitian ini juga menemukan "
    "bahwa kepercayaan kepada lembaga keuangan syariah memperkuat hubungan antara literasi dan minat pembiayaan."
)
SOURCE = {"kind": "korpus", "title": "Literasi keuangan syariah dan UMKM", "authors": ["Ahmad Rahman"], "year": "2019",
          "doi": "10.1/rahman", "file": "rahman.pdf", "text": SOURCE_TEXT}
OTHER = {"kind": "korpus", "title": "Topik lain", "authors": ["Budi Siregar"], "year": "2021", "doi": "10.1/siregar",
         "file": "siregar.pdf", "text": "Pembiayaan mikro di desa tumbuh cepat setelah program pemerintah dimulai pada tahun itu."}

COPY = ("literasi keuangan syariah memiliki pengaruh positif dan signifikan terhadap keputusan pelaku usaha mikro "
        "dalam memilih produk pembiayaan berbasis bagi hasil")

PARAGRAPHS = [
    {"n": 1, "text": f"Menurut pengamatan awal, {COPY}. Penulis kemudian mewawancarai dua belas pedagang pasar di Bandung."},
    {"n": 2, "text": f"Temuan sebelumnya menyatakan {COPY} (Siregar, 2021)."},
    {"n": 3, "text": f"Rahman (2019) menunjukkan bahwa {COPY}."},
    {"n": 4, "text": f"Rahman (2019, hlm. 4) menulis: “{COPY}”. Kutipan langsung ini diberi tanda petik dengan benar."},
    {"n": 5, "text": f"Dengan demikian {COPY}. Hal ini sejalan dengan Rahman (2019)."},
    {"n": 6, "text": "Hasil penelitian ini menunjukkan bahwa terdapat hubungan antara variabel yang diteliti dalam sampel."},
]


class TestText(unittest.TestCase):
    def test_split_sentences_keeps_abbreviations(self):
        s = similarity.split_sentences("Menurut Rahman dkk. (2019) literasi penting. Kalimat kedua. Ketiga!")
        self.assertEqual(s, ["Menurut Rahman dkk. (2019) literasi penting.", "Kalimat kedua.", "Ketiga!"])

    def test_checkable_words_drop_quotes_and_citations(self):
        ws = similarity.checkable_words("Ia menulis “teks kutipan langsung” seperti kata Rahman (2019) (Siregar, 2021).")
        self.assertEqual(ws, ["ia", "menulis", "seperti", "kata"])


class TestCheck(unittest.TestCase):
    def setUp(self):
        self.sim = similarity.check(PARAGRAPHS, online=False, sources=[SOURCE, OTHER])
        self.by_par = {f["paragraph"]: f for f in self.sim["findings"]}

    def test_labels(self):
        self.assertEqual(self.by_par[1]["label"], similarity.NO_CITATION)
        self.assertEqual(self.by_par[2]["label"], similarity.WRONG_SOURCE)
        self.assertEqual(self.by_par[3]["label"], similarity.TOO_CLOSE)
        self.assertEqual(self.by_par[5]["label"], similarity.TOO_CLOSE)  # citation in the next sentence counts
        self.assertNotIn(4, self.by_par)  # quoted text is not counted
        self.assertNotIn(6, self.by_par)  # common phrasing, no source
        self.assertEqual(self.by_par[1]["source"]["title"], SOURCE["title"])
        self.assertIn("Siregar 2021", self.by_par[2]["cited_as"])

    def test_only_copied_sentence_is_flagged(self):
        self.assertEqual(sum(1 for f in self.sim["findings"] if f["paragraph"] == 1), 1)
        self.assertGreaterEqual(self.by_par[1]["match_pct"], 70)
        self.assertGreaterEqual(self.by_par[1]["run"], similarity.FLAG_RUN)

    def test_score_and_sources(self):
        self.assertGreater(self.sim["score"], 30)
        self.assertLess(self.sim["score"], 100)
        self.assertEqual(self.sim["top_sources"][0]["title"], SOURCE["title"])
        self.assertEqual([f["id"] for f in self.sim["findings"]], ["m1", "m2", "m3", "m4"])
        self.assertIn("Literasi keuangan syariah memiliki", self.by_par[1]["source_excerpt"])

    def test_language_and_weak_comparison(self):
        self.assertEqual(similarity.guess_lang(SOURCE_TEXT), "id")
        self.assertEqual(similarity.guess_lang("The effect of the treatment on the outcome is shown in this study, "
                                               "which was conducted with care and is reported by the authors."), "en")
        self.assertEqual(similarity.guess_lang("x y z"), "")

        # One Indonesian source (OTHER is one sentence, too short to tell): too few to trust a low score.
        self.assertEqual(self.sim["lang"], "id")
        self.assertEqual(self.sim["same_lang"], {"korpus": 1, "dikutip": 0})
        self.assertTrue(self.sim["weak"])
        self.assertIn("hanya 1 sumber yang berbahasa Indonesia dan setopik", similarity.weak_message(self.sim))

        english = {**OTHER, "text": "The effect of the treatment on the outcome is shown in this study, which was "
                                    "conducted with care and is reported by the authors of the paper."}
        sim = similarity.check(PARAGRAPHS, online=False, sources=[english] * 6)
        self.assertTrue(sim["weak"])  # six sources, none in Indonesian
        sim = similarity.check(PARAGRAPHS, online=False, sources=[SOURCE] * 5)
        self.assertFalse(sim["weak"])
        self.assertEqual(sim["relevant"]["korpus"], 5)

        # Indonesian, but about something else: does not count as a usable comparison.
        off_topic = {**OTHER, "text": (
            "Penelitian ini membahas perlindungan data pribadi mahasiswa dalam penggunaan teknologi informasi di "
            "perguruan tinggi. Kebocoran data pribadi dapat terjadi melalui sistem informasi akademik yang lemah. "
            "Perlindungan data pribadi memerlukan kesadaran pengguna dan kebijakan keamanan sistem informasi.") * 3}
        sim = similarity.check(PARAGRAPHS, online=False, sources=[off_topic] * 6)
        self.assertEqual((sim["same_lang"]["korpus"], sim["relevant"]["korpus"]), (6, 0))
        self.assertTrue(sim["weak"])
        self.assertIn("6 paper berbahasa Indonesia di koleksi topiknya berbeda", similarity.weak_message(sim))

    def test_no_sources(self):
        sim = similarity.check(PARAGRAPHS, online=False, sources=[])
        self.assertEqual((sim["score"], sim["findings"]), (0.0, []))

    def test_cited_abstracts_are_fetched(self):
        citations = {"references": [
            {"raw": "Rahman (2019) ...", "doi": "10.1/rahman", "status": "ok_corpus", "authors": "Rahman", "years": ["2019"]},
            {"raw": "Lubis (2020) ...", "doi": "10.9/lubis", "status": "ok_crossref", "authors": "Lubis, C.",
             "years": ["2020"], "matched_title": "Studi Lubis"},
            {"raw": "Nasution (2018) ...", "doi": "10.9/nasution", "status": "ok_crossref", "authors": "Nasution",
             "years": ["2018"]},
            {"raw": "Buku lama", "doi": "", "status": "not_found"},
        ]}
        asked = []

        def fetch(doi):
            asked.append(doi)
            return SOURCE_TEXT if doi == "10.9/lubis" else ""

        sources, missed = similarity.cited_sources(citations, [SOURCE], fetch)
        self.assertEqual(asked, ["10.9/lubis", "10.9/nasution"])
        self.assertEqual(missed, 1)
        self.assertEqual((sources[0]["title"], sources[0]["year"], sources[0]["kind"]), ("Studi Lubis", "2020", "dikutip"))


DRAFT = "\n\n".join(["# Bab 2", "## Landasan Teori"] + [p["text"] for p in PARAGRAPHS] + [
    "DAFTAR PUSTAKA",
    "Rahman, A. (2019). Literasi keuangan syariah dan UMKM. Jurnal Ekonomi Islam, 4(2), 10-20.",
])


class TestReviewIntegration(unittest.TestCase):
    def setUp(self):
        self._old = config.ROOT
        self._tmp = tempfile.TemporaryDirectory()
        config._set_root(Path(self._tmp.name) / "data")
        config.ensure_dirs()
        self._patch = mock.patch.object(similarity, "corpus_sources", lambda: [SOURCE, OTHER])
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        config._set_root(self._old)
        self._tmp.cleanup()

    def test_similarity_only_review(self):
        r = review.review_text(DRAFT, title="Draf Uji", online=False, feedback=False,
                               chat=lambda *a, **k: self.fail("AI must not be called"))
        self.assertEqual(r["comments"], [])
        self.assertTrue(review.is_ready(r))
        self.assertEqual(r["summary"]["similarity_findings"], 4)

        first = r["similarity"]["findings"][0]
        similarity.set_hidden(r["similarity"], first["id"], True)
        r["summary"] = review.summarize(r)
        self.assertEqual(r["summary"]["similarity_findings"], 3)

        internal = review.report_markdown(r, final=False)
        self.assertIn("## Pemeriksaan kemiripan", internal)
        self.assertIn("Teks sumber:", internal)
        self.assertIn("Disembunyikan dari dokumen mahasiswa", internal)
        self.assertNotIn("## Komentar per paragraf", internal)

        self.assertIn("Pembanding lemah", internal)
        final = review.report_markdown(r, final=True)
        self.assertIn("bukan skor Turnitin", final)
        self.assertIn("sumber pembanding berbahasa Indonesia masih sedikit", final)
        self.assertNotIn("Panen Paper", final)
        self.assertNotIn("Teks sumber:", final)
        self.assertNotIn(first["sentence"], final)
        self.assertIn(similarity.LABELS[similarity.WRONG_SOURCE], final)

        # A rerun keeps what the consultant hid.
        review.save(r)
        again = review.run_similarity(review.load(r["stem"]), online=False)
        self.assertTrue([f for f in again["similarity"]["findings"] if f["sentence"] == first["sentence"]][0]["hidden"])
        self.assertTrue(review.export_docx(again, "Konsultan Uji").exists())

    def test_both_off_is_refused(self):
        with self.assertRaises(ValueError):
            review.review_text(DRAFT, online=False, feedback=False, similarity=False)

    def test_old_review_cannot_rerun(self):
        with self.assertRaises(ValueError):
            review.run_similarity({"citations": {"references": []}})


if __name__ == "__main__":
    unittest.main()
