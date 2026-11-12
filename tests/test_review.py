import json
import tempfile
import unittest
from pathlib import Path

from cosmolab import config, review

DRAFT = """# Bab 2 Tinjauan Pustaka

## Landasan Teori

Literasi keuangan syariah berpengaruh pada keputusan pembiayaan UMKM, seperti ditunjukkan oleh Rahman (2019) dalam studinya di Jawa Barat.

Banyak ahli setuju bahwa pembiayaan mikro selalu meningkatkan kesejahteraan, sehingga hipotesis penelitian ini pasti terbukti (Siregar, 2021).

Pendek.

DAFTAR PUSTAKA

Rahman, A. (2019). Literasi keuangan syariah dan UMKM. Jurnal Ekonomi Islam, 4(2), 10-20.
"""


def fake_chat(messages, model=None):
    user = messages[-1]["content"]
    assert "P1" in user and "P2" in user
    assert "Pendek." not in user  # too short to review
    assert "Rahman, A. (2019). Literasi" not in user  # reference list is not sent as a paragraph
    return json.dumps({
        "comments": [
            {"paragraph": 2, "category": "argumen", "severity": "penting",
             "comment": "Klaim 'selalu' dan 'pasti terbukti' terlalu mutlak.", "question": "Bukti apa yang menunjukkan ini?"},
            {"paragraph": "P1", "category": "bukti", "severity": "saran", "comment": "Sebutkan temuan utamanya.", "question": ""},
            {"paragraph": 99, "category": "argumen", "severity": "penting", "comment": "Paragraf tidak ada.", "question": ""},
            {"paragraph": 1, "category": "aneh", "severity": "aneh", "comment": "Kategori tak dikenal.", "question": ""},
        ],
        "strengths": ["Topik relevan", "Topik relevan"],
        "priorities": ["Lunakkan klaim mutlak di P2"],
    })


class TestReview(unittest.TestCase):
    def setUp(self):
        self._old = config.ROOT
        self._tmp = tempfile.TemporaryDirectory()
        config._set_root(Path(self._tmp.name) / "data")
        config.ensure_dirs()

    def tearDown(self):
        config._set_root(self._old)
        self._tmp.cleanup()

    def test_paragraphs_skip_headings_short_lines_and_references(self):
        md = review.mark_reference_heading(DRAFT)
        self.assertIn("## DAFTAR PUSTAKA", md)
        paras = review.split_paragraphs(md)
        self.assertEqual([p["n"] for p in paras], [1, 2])
        self.assertEqual(paras[0]["section"], "Landasan Teori")

    def test_review_text(self):
        r = review.review_text(DRAFT, title="Draf Uji", level="s1", online=False, chat=fake_chat)
        self.assertEqual(len(r["comments"]), 3)  # paragraph 99 dropped
        self.assertEqual(r["comments"][0]["paragraph"], 1)
        odd = [c for c in r["comments"] if c["comment"] == "Kategori tak dikenal."][0]
        self.assertEqual((odd["category"], odd["severity"]), ("argumen", review.SARAN))
        self.assertEqual(r["strengths"], ["Topik relevan"])
        s = r["summary"]
        self.assertEqual(s["by_severity"][review.PENTING], 1)
        self.assertEqual(s["citations_missing"], 1)  # Siregar (2021) is not in the list
        self.assertEqual(s["references"], 1)

        md = review.report_markdown(r)
        self.assertIn("Pertanyaan pemandu: Bukti apa yang menunjukkan ini?", md)
        self.assertIn("Siregar, 2021", md)
        # Only the opening words are quoted, never a whole paragraph.
        self.assertNotIn("sehingga hipotesis penelitian ini pasti terbukti", md)

        paths = review.save(r)
        self.assertTrue(paths["md"].exists() and paths["json"].exists())
        self.assertEqual(review.load_saved()[0]["report"]["title"], "Draf Uji")

    def test_docx_input_and_export(self):
        from docx import Document

        doc = Document()
        doc.add_heading("Pendahuluan", level=1)
        for block in DRAFT.split("\n\n")[2:4]:
            doc.add_paragraph(block.strip())
        path = Path(self._tmp.name) / "draf.docx"
        doc.save(str(path))
        md = review.read_draft(path)
        self.assertIn("# Pendahuluan", md)

        r = review.review_file(path, online=False, chat=fake_chat)
        out = review.export_docx(r, "Konsultan Uji")
        self.assertTrue(out.exists() and out.suffix == ".docx")
        with self.assertRaises(ValueError):
            review.export_docx(r, " ")

    def test_empty_draft(self):
        with self.assertRaises(ValueError):
            review.review_text("# Judul saja", online=False, chat=fake_chat)

    def test_unsupported_format(self):
        p = Path(self._tmp.name) / "x.pdf"
        p.write_bytes(b"%PDF")
        with self.assertRaises(ValueError):
            review.read_draft(p)


if __name__ == "__main__":
    unittest.main()
