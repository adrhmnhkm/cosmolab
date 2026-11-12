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


if __name__ == "__main__":
    unittest.main()
