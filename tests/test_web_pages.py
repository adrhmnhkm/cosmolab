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
        self.assertTrue(any(b.label == "Unduh Markdown" for b in at.get("download_button")))


if __name__ == "__main__":
    unittest.main()
