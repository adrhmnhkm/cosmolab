import json
import tempfile
import unittest
from pathlib import Path

from cosmolab import config, defense

DRAFT = """# Pendahuluan

Penelitian ini menguji pengaruh literasi keuangan terhadap perilaku menabung mahasiswa di Yogyakarta pada tahun 2024.

Rumusan masalahnya adalah apakah literasi keuangan berpengaruh positif terhadap perilaku menabung mahasiswa tingkat akhir.

# Metode

Sampel penelitian berjumlah 312 mahasiswa yang dipilih dengan teknik purposive sampling dari tiga perguruan tinggi negeri.

# Hasil

Hasil regresi menunjukkan literasi keuangan berpengaruh positif dan signifikan terhadap perilaku menabung mahasiswa.

# Daftar Pustaka

Lusardi, A. (2014). The economic importance of financial literacy.
"""


def _questions_chat(messages, model=None):
    return json.dumps({"questions": [
        {"area": "metode", "question": "Mengapa memakai purposive sampling?",
         "quote": "dipilih dengan teknik purposive sampling dari tiga perguruan tinggi negeri",
         "looks_for": "Alasan pemilihan teknik dan akibatnya pada generalisasi."},
        {"area": "hasil", "question": "Seberapa besar pengaruhnya?",
         "quote": "literasi keuangan berpengaruh positif dan signifikan terhadap perilaku menabung", "looks_for": "x"},
        {"area": "teori", "question": "Teori apa yang dipakai?", "quote": "kalimat ini tidak ada di draf sama sekali ya",
         "looks_for": "x"},
        {"area": "aneh", "question": "", "quote": "Sampel penelitian berjumlah 312 mahasiswa"},
    ]})


class TestDefense(unittest.TestCase):
    def setUp(self):
        self._old = config.ROOT
        self._tmp = tempfile.TemporaryDirectory()
        config._set_root(Path(self._tmp.name) / "data")
        config.ensure_dirs()

    def tearDown(self):
        config._set_root(self._old)
        self._tmp.cleanup()

    def test_start_keeps_only_questions_quoting_the_draft(self):
        sent = {}

        def chat(messages, model=None):
            sent["user"] = messages[1]["content"]
            return _questions_chat(messages)

        s = defense.start(DRAFT, title="Tesis Rina", level="s2", n=5, source="rina.docx", chat=chat)
        self.assertNotIn("Lusardi", sent["user"])  # the reference list is not sent
        self.assertEqual([q["id"] for q in s["questions"]], ["q1", "q2"])
        self.assertEqual(s["dropped"], 1)  # the quote that is not in the draft
        self.assertEqual(s["questions"][0]["section"], "Metode")
        self.assertIn("312 mahasiswa", s["questions"][0]["context"])
        self.assertEqual(defense.load(s["stem"])["title"], "Tesis Rina")
        self.assertEqual(len(defense.load_saved()), 1)

    def test_short_draft_and_no_usable_question(self):
        with self.assertRaises(ValueError):
            defense.start("Terlalu pendek.", chat=_questions_chat)
        with self.assertRaises(ValueError):
            defense.start(DRAFT, chat=lambda m, model=None: '{"questions": []}')

    def test_answer_feedback_and_notes(self):
        s = defense.start(DRAFT, title="Tesis Rina", chat=_questions_chat)
        with self.assertRaises(ValueError):
            defense.answer(s, "q1", "pendek", chat=_questions_chat)
        with self.assertRaises(ValueError):  # unreadable score: nothing saved
            defense.answer(s, "q1", "x" * 60, chat=lambda m, model=None: '{"score": "bagus"}')
        self.assertIsNone(defense.load(s["stem"])["questions"][0]["feedback"])

        seen = {}

        def chat(messages, model=None):
            seen["system"], seen["user"] = messages[0]["content"], messages[1]["content"]
            return json.dumps({"score": "cukup", "strengths": ["Menyebut alasan akses"], "gaps": ["a", "b", "c", "d"],
                               "prepare": ["Baca lagi bab metode"], "follow_up": "Bagaimana generalisasinya?"})

        text = "Saya memilih purposive sampling karena hanya mahasiswa tingkat akhir yang sesuai kriteria penelitian."
        q = defense.answer(s, "q1", text, chat=chat)
        self.assertIn("JANGAN menuliskan jawaban", seen["system"])
        self.assertIn("312 mahasiswa", seen["user"])  # the draft paragraph goes with the answer
        self.assertEqual(q["feedback"]["score"], "cukup")
        self.assertEqual(len(q["feedback"]["gaps"]), 3)  # capped
        saved = defense.load(s["stem"])
        self.assertEqual(saved["questions"][0]["answer"], text)
        self.assertEqual(defense.progress(saved), {"total": 2, "answered": 1, "kuat": 0, "cukup": 1, "lemah": 0})
        md = defense.session_markdown(saved)
        self.assertIn("**Penilaian: Cukup**", md)
        self.assertIn("Pertanyaan lanjutan: Bagaimana generalisasinya?", md)

    def test_long_draft_is_trimmed(self):
        long = "\n\n".join(f"Paragraf nomor {i} berisi kalimat yang cukup panjang untuk dihitung sebagai isi draf." for i in range(2000))
        trimmed = defense.trim_draft(long, limit=5000)
        self.assertLess(len(trimmed), 5200)
        self.assertIn("Paragraf nomor 0 ", trimmed)
        self.assertIn("Paragraf nomor 1999 ", trimmed)
        self.assertEqual(trimmed.count("[... bagian dipotong ...]"), 2)


if __name__ == "__main__":
    unittest.main()
