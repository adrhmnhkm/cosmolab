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
            # exact quote, different case and punctuation: grounded
            {"paragraph": 2, "quote": "Pembiayaan mikro SELALU meningkatkan kesejahteraan,", "category": "argumen",
             "severity": "penting", "comment": "Klaim 'selalu' dan 'pasti terbukti' terlalu mutlak.",
             "question": "Bukti apa yang menunjukkan ini?"},
            # paraphrased quote: not grounded
            {"paragraph": "P1", "quote": "literasi finansial memengaruhi UMKM", "category": "bukti", "severity": "saran",
             "comment": "Sebutkan temuan utamanya.", "question": ""},
            {"paragraph": 99, "quote": "x y z", "category": "argumen", "severity": "penting",
             "comment": "Paragraf tidak ada.", "question": ""},
            # quote from another paragraph: not grounded for P1
            {"paragraph": 1, "quote": "hipotesis penelitian ini pasti terbukti", "category": "aneh", "severity": "aneh",
             "comment": "Kategori tak dikenal.", "question": ""},
        ],
        "strengths": ["Topik relevan", "Topik relevan"],
        "priorities": ["Lunakkan klaim mutlak di P2"],
    })


class TestQuoteCheck(unittest.TestCase):
    def test_quote_found(self):
        para = "Banyak ahli setuju bahwa pembiayaan mikro selalu meningkatkan kesejahteraan (Siregar, 2021)."
        self.assertTrue(review.quote_found("pembiayaan Mikro selalu meningkatkan kesejahteraan", para))
        self.assertTrue(review.quote_found("“ahli setuju bahwa”", para))
        self.assertFalse(review.quote_found("pembiayaan mikro kadang meningkatkan kesejahteraan", para))
        self.assertFalse(review.quote_found("ahli setuju", para))  # too short to prove anything
        self.assertFalse(review.quote_found("", para))


class TestReview(unittest.TestCase):
    def setUp(self):
        self._old = config.ROOT
        self._tmp = tempfile.TemporaryDirectory()
        config._set_root(Path(self._tmp.name) / "data")
        config.ensure_dirs()

    def tearDown(self):
        config._set_root(self._old)
        self._tmp.cleanup()

    def _review(self):
        return review.review_text(DRAFT, title="Draf Uji", level="s1", online=False, chat=fake_chat)

    def test_paragraphs_skip_headings_short_lines_and_references(self):
        md = review.mark_reference_heading(DRAFT)
        self.assertIn("## DAFTAR PUSTAKA", md)
        paras = review.split_paragraphs(md)
        self.assertEqual([p["n"] for p in paras], [1, 2])
        self.assertEqual(paras[0]["section"], "Landasan Teori")

    def test_review_text(self):
        r = self._review()
        self.assertEqual(len(r["comments"]), 3)  # paragraph 99 dropped
        self.assertEqual([c["id"] for c in r["comments"]], ["k1", "k2", "k3"])
        self.assertEqual(r["comments"][0]["paragraph"], 1)
        self.assertTrue(all(c["decision"] == review.PENDING for c in r["comments"]))
        grounded = {c["comment"]: c["grounded"] for c in r["comments"]}
        self.assertTrue(grounded["Klaim 'selalu' dan 'pasti terbukti' terlalu mutlak."])
        self.assertFalse(grounded["Sebutkan temuan utamanya."])
        self.assertFalse(grounded["Kategori tak dikenal."])
        odd = [c for c in r["comments"] if c["comment"] == "Kategori tak dikenal."][0]
        self.assertEqual((odd["category"], odd["severity"]), ("argumen", review.SARAN))
        self.assertEqual(r["strengths"], ["Topik relevan"])
        s = r["summary"]
        self.assertEqual(s["ungrounded"], 2)
        self.assertEqual(s["by_severity"][review.PENTING], 1)
        self.assertEqual(s["citations_missing"], 1)  # Siregar (2021) is not in the list
        self.assertEqual(s["references"], 1)

        internal = review.report_markdown(r)
        self.assertIn("Versi internal, belum final", internal)
        self.assertIn("KUTIPAN TIDAK DITEMUKAN", internal)
        self.assertIn("Pertanyaan pemandu: Bukti apa yang menunjukkan ini?", internal)
        self.assertIn("Siregar, 2021", internal)
        # Only the opening words and short quotes appear, never a whole paragraph.
        self.assertNotIn("pasti terbukti (Siregar, 2021)", internal)

    def test_decisions_control_what_the_student_sees(self):
        r = self._review()
        review.save(r)
        stem = r["stem"]
        with self.assertRaises(ValueError):
            review.export_docx(r, "Konsultan Uji")  # nothing decided yet

        self.assertEqual(review.accept_grounded(r), 1)
        ungrounded = [c["id"] for c in r["comments"] if not c["grounded"]]
        review.set_decision(r, ungrounded[0], review.EDIT, comment="Jelaskan temuan Rahman (2019).", question="Apa temuannya?")
        self.assertFalse(review.is_ready(r))
        review.set_decision(r, ungrounded[1], review.DROP)
        self.assertTrue(review.is_ready(r))
        with self.assertRaises(ValueError):
            review.set_decision(r, ungrounded[0], review.EDIT, comment="  ")
        with self.assertRaises(ValueError):
            review.set_decision(r, ungrounded[0], "setuju")

        final = review.report_markdown(r)
        self.assertNotIn("Versi internal", final)
        self.assertIn("Jelaskan temuan Rahman (2019).", final)
        self.assertNotIn("Sebutkan temuan utamanya.", final)  # replaced by the edit
        self.assertNotIn("Kategori tak dikenal.", final)  # dropped
        self.assertNotIn("KUTIPAN", final)
        self.assertIn("2 komentar", final)

        paths = review.save(r)
        self.assertEqual(paths["json"].stem, stem)  # same files, not a new review
        self.assertEqual(len(list(review.reviews_dir().glob("*.json"))), 1)
        again = review.load(stem)
        self.assertEqual(review.decision_counts(again),
                         {review.PENDING: 0, review.ACCEPT: 1, review.EDIT: 1, review.DROP: 1})
        self.assertEqual(review.load_saved()[0]["report"]["title"], "Draf Uji")

        out = review.export_docx(again, "Konsultan Uji")
        self.assertTrue(out.exists() and out.suffix == ".docx")
        with self.assertRaises(ValueError):
            review.export_docx(again, " ")

    def test_old_saved_review_gets_defaults(self):
        r = self._review()
        for c in r["comments"]:
            for k in ("id", "decision", "quote", "grounded"):
                c.pop(k)
        review.save(r)
        loaded = review.load(r["stem"])
        self.assertEqual(loaded["comments"][0]["id"], "k1")
        self.assertEqual(loaded["comments"][0]["decision"], review.PENDING)
        self.assertFalse(loaded["comments"][0]["grounded"])

    def test_docx_input(self):
        from docx import Document

        doc = Document()
        doc.add_heading("Pendahuluan", level=1)
        for block in DRAFT.split("\n\n")[2:4]:
            doc.add_paragraph(block.strip())
        path = Path(self._tmp.name) / "draf.docx"
        doc.save(str(path))
        self.assertIn("# Pendahuluan", review.read_draft(path))
        r = review.review_file(path, online=False, chat=fake_chat)
        self.assertEqual(r["title"], "draf")

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
