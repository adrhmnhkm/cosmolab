import unittest

from cosmolab import entail

PAPERS = [
    {"file": "a.pdf", "title": "Causality and Nonlocality as Axioms for Quantum Mechanics", "year": "1997",
     "authors": '["Sandu Popescu", "Daniel Rohrlich"]', "thesis": "Kausalitas dan nonlokalitas tidak cukup."},
    {"file": "b.pdf", "title": "Etika Bisnis Islam dalam UMKM", "year": "2021", "authors": '["Siti Aminah"]'},
]


def fake_evidence(claim, paper):
    return [{"paper": paper["title"], "page_label": "Hal. 2", "text": "bukti " + paper["file"]}]


class SplitClaimsTests(unittest.TestCase):
    def test_period_inside_citation_does_not_split(self):
        claims = entail.split_claims("Korelasi kuantum melanggar batas hingga 4 [Causality (1997), Hal. 2]. Lanjut.")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["citations"][0]["page"], "2")
        self.assertEqual(claims[0]["text"], "Korelasi kuantum melanggar batas hingga 4.")

    def test_trailing_citation_joins_previous_sentence(self):
        claims = entail.split_claims("Klaim ini cukup panjang untuk dicek. [Smith (2001); Lee, 2003, p. 4]")
        self.assertEqual(len(claims), 1)
        self.assertEqual([(c["label"], c["year"], c["page"]) for c in claims[0]["citations"]],
                         [("Smith", "2001", ""), ("Lee", "2003", "4")])

    def test_ignores_headings_links_and_uncited_sentences(self):
        text = "## Judul [Bab (2020)]\nKalimat tanpa sumber sama sekali.\n- Lihat [situs](http://x.org) saja."
        self.assertEqual(entail.split_claims(text), [])

    def test_citation_as_subject_keeps_names(self):
        claims = entail.split_claims("[Popescu & Rohrlich (1997)] membantah tuduhan paradoks kausal.\n"
                                     "Menurut [Aminah (2021)], etika bisnis menjadi dasar UMKM.")
        self.assertEqual([c["text"] for c in claims], [
            "Popescu & Rohrlich membantah tuduhan paradoks kausal.",
            "Menurut Aminah, etika bisnis menjadi dasar UMKM.",
        ])

    def test_source_header_and_abbreviations(self):
        text = ("1. **[Popescu & Rohrlich (1997)]** — Bagian I (Introduction), hlm. 1:\n"
                "Relativitas khusus diturunkan dari dua aksioma, lihat hlm. 3 untuk rinciannya [Popescu (1997)].")
        claims = entail.split_claims(text)
        self.assertEqual(len(claims), 1)
        self.assertTrue(claims[0]["text"].startswith("Relativitas khusus"))
        self.assertIn("hlm. 3 untuk rinciannya", claims[0]["text"])

    def test_markdown_is_stripped(self):
        claims = entail.split_claims("- **Tesis utama** ditolak oleh kritikus [Aminah (2021)].")
        self.assertEqual(claims[0]["text"], "Tesis utama ditolak oleh kritikus.")


class MatchPaperTests(unittest.TestCase):
    def test_by_title_prefix(self):
        cite = entail.parse_citation("Causality and Nonlocality (1997)")[0]
        self.assertEqual(entail.match_paper(cite, PAPERS)["file"], "a.pdf")

    def test_by_author_surname(self):
        cite = entail.parse_citation("Popescu & Rohrlich (1997)")[0]
        self.assertEqual(entail.match_paper(cite, PAPERS)["file"], "a.pdf")

    def test_year_must_match(self):
        cite = entail.parse_citation("Popescu (2005)")[0]
        self.assertIsNone(entail.match_paper(cite, PAPERS))


class GatherEvidenceTests(unittest.TestCase):
    def test_skips_bibliography_and_author_terms(self):
        from unittest import mock
        from cosmolab import retrieval

        queries = []

        def fake_find(file, query, top_k=2, max_length=400):
            queries.append(query)
            return [{"page_label": "Halaman 8", "verbatim": "[12] J. Grunhaus, S. Popescu, Phys. Rev. A53 (1996) 3781."},
                    {"page_label": "Halaman 5", "verbatim": "violate the CHSH inequality with the maximal value 4."}]

        with mock.patch.object(retrieval, "find_grounded_passages", side_effect=fake_find):
            ev = entail.gather_evidence("klaim", PAPERS[0], extra_query="Popescu Rohrlich CHSH maximum 4")
        self.assertEqual(queries[1], "CHSH maximum 4")
        pages = [e["page_label"] for e in ev]
        self.assertNotIn("Halaman 8", pages)
        self.assertEqual(pages, ["Halaman 5", "Tesis (analisis)"])


class CheckAnswerTests(unittest.TestCase):
    def test_verdicts_and_missing_source(self):
        seen = {}

        def judge(items, model):
            seen["ids"] = [it["id"] for it in items]
            return {1: {"verdict": "didukung", "reason": "cocok", "evidence": ["E1"]},
                    2: {"verdict": "Tidak didukung", "reason": "tidak ada", "evidence": ["E9"]}}

        text = ("Kausalitas tidak cukup menurunkan mekanika kuantum [Popescu (1997)]. "
                "UMKM syariah selalu untung dua kali lipat [Aminah (2021)]. "
                "Eksperimen Delft membuktikannya [Hensen (2015)].")
        r = entail.check_answer(text, PAPERS, judge=judge, evidence_fn=fake_evidence)
        self.assertEqual(seen["ids"], [1, 2])
        verdicts = [c["verdict"] for c in r["claims"]]
        self.assertEqual(verdicts, [entail.SUPPORTED, entail.UNSUPPORTED, entail.NO_SOURCE])
        self.assertEqual(r["claims"][0]["evidence_used"], [0])
        self.assertEqual(r["claims"][1]["evidence_used"], [])  # E9 does not exist
        self.assertEqual(entail.needs_attention(r), 2)

    def test_judge_failure_leaves_claims_unchecked(self):
        def judge(items, model):
            raise RuntimeError("gateway down")

        r = entail.check_answer("Kausalitas tidak cukup sama sekali [Popescu (1997)].", PAPERS,
                                judge=judge, evidence_fn=fake_evidence)
        self.assertEqual(r["claims"][0]["verdict"], entail.UNCHECKED)
        self.assertIn("gateway down", r["claims"][0]["reason"])

    def test_paper_number_uses_answer_order(self):
        text = "Etika bisnis diterapkan pada UMKM [Paper 2 (2021)]. Klaim lain yang panjang [Paper 7 (2021)]."
        r = entail.check_answer(text, PAPERS, numbered=[PAPERS[0], {"file": "b.pdf"}],
                                judge=lambda items, m: {}, evidence_fn=fake_evidence)
        self.assertEqual(r["claims"][0]["papers"][0]["file"], "b.pdf")
        self.assertEqual(r["claims"][0]["papers"][0]["title"], PAPERS[1]["title"])
        self.assertEqual(r["claims"][1]["verdict"], entail.NO_SOURCE)

    def test_max_claims(self):
        text = " ".join(f"Klaim nomor {i} cukup panjang [Popescu (1997)]." for i in range(5))
        r = entail.check_answer(text, PAPERS, max_claims=3, judge=lambda items, m: {}, evidence_fn=fake_evidence)
        self.assertEqual((r["total"], r["skipped"]), (3, 2))


if __name__ == "__main__":
    unittest.main()
