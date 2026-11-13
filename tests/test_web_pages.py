"""Render every dashboard page headlessly and check none of them raises.

Buttons are not clicked, so no AI calls are made. web.py reloads cosmolab
modules on each run, and reloading config would point it back at the real
data folder; importlib.reload is patched out so the test data copy from
conftest stays in use.
"""

import unittest
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from cosmolab import review

WEB = str(Path(__file__).resolve().parent.parent / "cosmolab" / "web.py")

PAGES = [
    "Paper Explorer & Korpus",
    "Roadmap Belajar & Kurikulum",
    "Arena Sparring Nalar",
    "Tanya Korpus & Sintesis",
    "Review Draf Mahasiswa",
    "Studio Artikel Siap Baca",
    "Bedah DOI Seketika",
    "Panen Paper Ilmiah",
    "Full-Text Search",
    "Diagram Argumen",
    "Laporan Sintesis",
    "Pusat Akurasi",
    "Ekspor Data & Flashcards",
]


class TestWebPages(unittest.TestCase):
    def test_every_page_renders(self):
        for page in PAGES:
            with self.subTest(page=page), mock.patch("importlib.reload", lambda m: m):
                at = AppTest.from_file(WEB, default_timeout=120)
                at.session_state["active_nav_menu"] = page
                at.run()
                self.assertEqual([e.value for e in at.exception], [], page)
                self.assertGreater(len(at.markdown), 0, page)

    def test_sinta_tab_adds_a_journal(self):
        from cosmolab import sinta

        with mock.patch("importlib.reload", lambda m: m):
            at = AppTest.from_file(WEB, default_timeout=120)
            at.session_state["active_nav_menu"] = "Panen Paper Ilmiah"
            at.run()
            [t for t in at.text_input if t.label == "Nama jurnal"][0].input("Jurnal Uji")
            [t for t in at.text_input if t.label.startswith("ISSN")][0].input("2087-1236")
            [s for s in at.selectbox if s.label == "Peringkat"][0].set_value(2)
            [b for b in at.button if b.label == "Simpan"][0].click()
            at.run()
        try:
            self.assertEqual([e.value for e in at.exception], [])
            self.assertIn("SINTA 2 ditambahkan", " ".join(s.value for s in at.success))
            self.assertEqual(sinta.rank_for(["2087-1236"])["name"], "Jurnal Uji")
        finally:
            sinta.remove("2087-1236")

    def test_review_page_similarity_only(self):
        from test_similarity import DRAFT, OTHER, SOURCE

        from cosmolab import similarity

        with mock.patch("importlib.reload", lambda m: m), \
                mock.patch.object(similarity, "corpus_sources", lambda: [SOURCE, OTHER]), \
                mock.patch("cosmolab.review._default_chat", side_effect=AssertionError("AI must not be called")):
            at = AppTest.from_file(WEB, default_timeout=120)
            at.session_state["active_nav_menu"] = "Review Draf Mahasiswa"
            at.run()
            at.text_area[0].input(DRAFT)
            [t for t in at.toggle if t.label == "Cek sitasi ke Crossref"][0].set_value(False)
            [c for c in at.checkbox if c.label == "Komentar pembimbing (AI)"][0].uncheck()
            [b for b in at.button if b.label == "Review draf"][0].click()
            at.run()
            self.assertEqual([e.value for e in at.exception], [])
            self.assertEqual([e.value for e in at.error], [])
            stem = at.session_state["review_current"]
            text = " ".join(m.value for m in at.markdown)
            self.assertIn("Perkiraan kemiripan", text)

            first = review.load(stem)["similarity"]["findings"][0]["id"]
            at.checkbox(key=f"rv_new_{stem}_{first}_h").check()
            at.run()
            at.text_input(key=f"rv_new_{stem}_reviewer").input("Konsultan Uji")
            at.button(key=f"rv_new_{stem}_docx_btn").click()
            at.run()

            # Fill in cited works: nothing is open in this test, so the book is listed for the student.
            from cosmolab import harvest

            with mock.patch.object(harvest, "_resolve_unpaywall", lambda doi: None), \
                    mock.patch.object(harvest, "_search_openalex", lambda *a, **k: []), \
                    mock.patch.object(harvest, "_search_semanticscholar", lambda *a, **k: []), \
                    mock.patch.object(harvest, "_search_doaj", lambda *a, **k: []), \
                    mock.patch.object(harvest, "_search_core", lambda *a, **k: []), \
                    mock.patch.object(similarity, "_cached_abstract", lambda doi: ""):
                at.button(key=f"rv_new_{stem}_fill").click()
                at.run()

        self.assertEqual([e.value for e in at.exception], [])
        self.assertTrue(any(b.label.startswith("Unduh Word") for b in at.get("download_button")))
        saved = review.load(stem)
        self.assertTrue([f for f in saved["similarity"]["findings"] if f["id"] == first][0]["hidden"])
        self.assertEqual(saved["summary"]["similarity_findings"], len(saved["similarity"]["findings"]) - 1)
        self.assertTrue(saved["coverage"]["items"])
        self.assertIn("tidak bisa dibandingkan", " ".join(m.value for m in at.markdown))

    def test_review_page_runs_a_review(self):
        from test_review import DRAFT, fake_chat

        with mock.patch("importlib.reload", lambda m: m), mock.patch("cosmolab.review._default_chat", fake_chat):
            at = AppTest.from_file(WEB, default_timeout=120)
            at.session_state["active_nav_menu"] = "Review Draf Mahasiswa"
            at.run()
            at.text_area[0].input(DRAFT)
            [t for t in at.toggle if t.label == "Cek sitasi ke Crossref"][0].set_value(False)
            [b for b in at.button if b.label == "Review draf"][0].click()
            at.run()
            self.assertEqual([e.value for e in at.exception], [])
            self.assertEqual([e.value for e in at.error], [])
            text = " ".join(m.value for m in at.markdown)
            self.assertIn("Bukti apa yang menunjukkan ini?", text)

            stem = at.session_state["review_current"]
            k = lambda cid, part: f"rv_new_{stem}_{cid}_{part}"  # noqa: E731

            # Word is refused while comments are undecided.
            at.text_input(key=f"rv_new_{stem}_reviewer").input("Konsultan Uji")
            at.button(key=f"rv_new_{stem}_docx_btn").click()
            at.run()
            self.assertIn("belum diputuskan", " ".join(w.value for w in at.warning))

            # Accept the one comment whose quote matched, edit one, drop one.
            at.button(key=f"rv_new_{stem}_bulk").click()
            at.run()
            self.assertEqual(at.radio(key=k("k3", "d")).value, review.ACCEPT)
            at.radio(key=k("k1", "d")).set_value(review.EDIT)
            at.run()
            at.text_area(key=k("k1", "c")).input("Komentar hasil edit konsultan.")
            at.run()
            at.radio(key=k("k2", "d")).set_value(review.DROP)
            at.run()

            at.button(key=f"rv_new_{stem}_docx_btn").click()
            at.run()

        self.assertEqual([e.value for e in at.exception], [])
        self.assertEqual([w.value for w in at.warning if "komentar" in w.value], [])
        self.assertTrue(any(b.label.startswith("Unduh Word") for b in at.get("download_button")))
        saved = review.load(stem)
        self.assertEqual(review.decision_counts(saved),
                         {review.PENDING: 0, review.ACCEPT: 1, review.EDIT: 1, review.DROP: 1})
        final = review.report_markdown(saved)
        self.assertIn("Komentar hasil edit konsultan.", final)
        self.assertNotIn("Kategori tak dikenal.", final)


if __name__ == "__main__":
    unittest.main()
