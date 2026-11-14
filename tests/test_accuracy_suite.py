import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cosmolab import analysis_check, audit, config, corrections, entail, evaluate, metadata

ANALYSIS = {
    "thesis": "Kausalitas dan nonlokalitas tidak cukup untuk menurunkan mekanika kuantum.",
    "conclusion": "Perlu aksioma tambahan di luar kausalitas relativistik.",
    "premises": ["Relativitas khusus diturunkan dari dua aksioma.", "Korelasi PR melanggar CHSH hingga nilai 4."],
    "key_findings": ["Ada teori nonlokal yang kausal selain mekanika kuantum."],
    "quotes": [
        {"text": "Special relativity can be deduced in its entirety from two axioms", "page_hint": "hlm. 1"},
        {"text": "This sentence was never written by the authors of the paper", "page_hint": "hlm. 2"},
    ],
}
PAGES = [
    {"page": 1, "text": "Abstract. Special relativity can be de- duced in its entirety from two axioms: the equivalence."},
    {"page": 2, "text": "Quantum correlations violate the CHSH inequality, reaching 2 sqrt 2."},
]
PAPER = {"file": "p.pdf", "title": "Causality and Nonlocality", "year": "1997", "authors": '["Sandu Popescu"]',
         "doi": "10.1000/x"}


class TempRoot(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = config.ROOT
        config._set_root(Path(self._tmp.name))

    def tearDown(self):
        config._set_root(self._old)
        self._tmp.cleanup()


class AnalysisCheckTests(TempRoot):
    def test_statements_cover_text_and_list_fields(self):
        st = analysis_check.statements(ANALYSIS)
        self.assertEqual([(s["field"], s["index"]) for s in st],
                         [("thesis", None), ("conclusion", None), ("premises", 0), ("premises", 1), ("key_findings", 0)])

    def test_quote_found_across_hyphenation_and_invented_quote_missing(self):
        q = analysis_check.check_quotes(ANALYSIS, PAGES)
        self.assertEqual(q[0]["status"], analysis_check.QUOTE_FOUND)
        self.assertEqual(q[0]["page"], 1)
        self.assertTrue(q[0]["page_ok"])
        self.assertEqual(q[1]["status"], analysis_check.QUOTE_MISSING)

    def test_check_paper_judges_without_the_analysis_as_evidence(self):
        seen = {}

        def judge(items, model):
            seen["n"] = seen.get("n", 0) + len(items)
            return {it["id"]: {"verdict": "didukung" if it["id"] == 3 else "sebagian", "reason": "r", "evidence": ["E1"]}
                    for it in items}

        def evidence(claim, paper):
            return [{"paper": "x", "page_label": "Halaman 1", "text": "teks asli"}]

        r = analysis_check.check_paper("p.pdf", analysis=ANALYSIS, pages=PAGES, paper=PAPER,
                                       judge=judge, evidence_fn=evidence)
        self.assertEqual(seen["n"], 5)
        self.assertEqual(r["summary"], {"sebagian": 4, "didukung": 1})
        self.assertEqual(r["statements"][2]["label"], "Premis")
        self.assertTrue(analysis_check.check_path("p.pdf").exists())
        self.assertEqual(analysis_check.score(analysis_check.load_check("p.pdf"))["quotes_found"], 1)

    def test_gather_evidence_can_leave_out_analysis(self):
        with mock.patch("cosmolab.retrieval.find_grounded_passages", return_value=[]):
            ev = entail.gather_evidence("klaim", {"file": "p.pdf", "thesis": "tesis AI"}, use_analysis=False)
            self.assertEqual(ev, [])
            ev = entail.gather_evidence("klaim", {"file": "p.pdf", "thesis": "tesis AI"})
            self.assertEqual(ev[0]["text"], "tesis AI")


class CorrectionTests(TempRoot):
    def test_edit_wrong_and_correct(self):
        corrections.set_review("p.pdf", "thesis", None, corrections.EDITED, value="Tesis baru.", analysis=ANALYSIS)
        corrections.set_review("p.pdf", "premises", 1, corrections.WRONG, analysis=ANALYSIS)
        corrections.set_review("p.pdf", "premises", 0, corrections.CORRECT, analysis=ANALYSIS)
        out = corrections.apply("p.pdf", ANALYSIS)
        self.assertEqual(out["thesis"], "Tesis baru.")
        self.assertEqual(out["premises"], ["Relativitas khusus diturunkan dari dua aksioma."])
        self.assertEqual(out["_review"]["premises.0"], corrections.CORRECT)
        self.assertEqual(ANALYSIS["premises"][1], "Korelasi PR melanggar CHSH hingga nilai 4.")  # original untouched
        self.assertEqual(audit.read(event="koreksi")[0]["field"], "premises.0")

    def test_stale_after_reanalysis(self):
        corrections.set_review("p.pdf", "thesis", None, corrections.WRONG, analysis=ANALYSIS)
        new = dict(ANALYSIS, thesis="Tesis hasil analisis ulang yang berbeda.")
        out = corrections.apply("p.pdf", new)
        self.assertEqual(out["thesis"], new["thesis"])
        self.assertEqual(out["_review"]["thesis"], "kedaluwarsa")
        self.assertEqual(corrections.summary("p.pdf", new)["stale"], 1)

    def test_edit_needs_text(self):
        with self.assertRaises(ValueError):
            corrections.set_review("p.pdf", "thesis", None, corrections.EDITED, value=" ", analysis=ANALYSIS)


CROSSREF_ITEM = {
    "title": ["Causality and nonlocality as axioms for quantum mechanics"],
    "author": [{"given": "Sandu", "family": "Popescu"}, {"given": "Daniel", "family": "Rohrlich"}],
    "issued": {"date-parts": [[1998]]},
    "container-title": ["Foundations of Physics"], "volume": "28", "page": "1-10", "type": "journal-article",
    "DOI": "10.1000/x",
    "updated-by": [{"type": "retraction", "label": "Retraction", "DOI": "10.1000/r", "updated": {"date-parts": [[2020]]}}],
}


class MetadataTests(TempRoot):
    def test_year_difference_and_retraction(self):
        r = metadata.check_paper(PAPER, fetch=lambda d: CROSSREF_ITEM, retracted_fn=lambda d: False)
        self.assertEqual(r["status"], metadata.DIFF)
        self.assertEqual([d["field"] for d in r["diffs"]], ["tahun"])
        self.assertTrue(r["notices"][0]["serious"])
        self.assertEqual(metadata.flagged({"p.pdf": r})[0]["file"], "p.pdf")

    def test_unknown_doi(self):
        r = metadata.check_paper(PAPER, fetch=lambda d: None, retracted_fn=lambda d: False, registered_fn=lambda d: False)
        self.assertEqual(r["status"], metadata.INVALID)
        self.assertEqual(metadata.check_paper({"file": "a"}, fetch=lambda d: None)["status"], metadata.NO_DOI)

    def test_bibtex_uses_verified_record_and_warns(self):
        ok = dict(CROSSREF_ITEM, issued={"date-parts": [[1997]]}, **{"updated-by": []})
        r = metadata.check_paper(PAPER, fetch=lambda d: ok, retracted_fn=lambda d: False)
        bib = metadata.to_bibtex([PAPER, {"file": "b.pdf", "title": "Lain", "year": "2020"}],
                                 {"p.pdf": r})
        self.assertIn("@article{popescu1997causality", bib)
        self.assertIn("author = {Sandu Popescu and Daniel Rohrlich}", bib)
        self.assertIn("journal = {Foundations of Physics}", bib)
        self.assertIn("pages = {1--10}", bib)
        self.assertIn("Metadata belum diverifikasi", bib)  # second paper
        ris = metadata.to_ris([PAPER], {"p.pdf": r})
        self.assertIn("AU  - Daniel Rohrlich", ris)
        self.assertIn("EP  - 10", ris)


class EvaluateTests(TempRoot):
    def test_draft_and_run(self):
        drafter = lambda passage, model: {"question": "Apa isi?", "true_claim": "Benar.", "false_claim": "Salah."}
        long = "The equivalence principle and the constancy of light give special relativity. " * 5
        with mock.patch("cosmolab.extract.get_paper_pages", return_value=[{"page": 2, "paragraphs": [long]}]):
            new = evaluate.draft_gold(n_papers=1, drafter=drafter, papers=[PAPER])
        self.assertEqual([it["kind"] for it in new], ["retrieval", "claim", "claim"])
        self.assertEqual(len(evaluate.load_gold()), 3)

        judge = lambda items, model: {it["id"]: {"verdict": "didukung", "reason": ""} for it in items}
        hits = [{"page": 2, "page_label": "Halaman 2", "verbatim": "x"}]
        with mock.patch("cosmolab.retrieval.find_grounded_passages", return_value=hits), \
                mock.patch("cosmolab.db.get_all_papers_with_analyses", return_value=[PAPER]):
            r = evaluate.run(k=3, expand=False, rerank=False, judge=judge,
                             evidence_fn=lambda c, p: [{"paper": "x", "page_label": "", "text": "t"}])
        self.assertEqual(r["retrieval"]["recall_at_k"], 1.0)
        self.assertEqual(r["claims"]["accuracy"], 0.5)
        self.assertEqual(r["claims"]["false_caught"], 0.0)
        self.assertEqual(r["claims"]["true_passed"], 1.0)
        self.assertEqual(len(evaluate.history()), 1)
        self.assertEqual(audit.read(event="evaluasi")[0]["n_claims"], 2)


class AuditTests(TempRoot):
    def test_log_read_csv_and_methods(self):
        audit.log("tanya", question="Apa itu kalam?", model="m1")
        audit.log("analisis", file="a.pdf", model="m2")
        rows = audit.read()
        self.assertEqual([r["event"] for r in rows], ["analisis", "tanya"])
        self.assertIn("Apa itu kalam?", audit.to_csv(rows))
        text = audit.methods_text(rows)
        self.assertIn("2 langkah", text)
        self.assertIn("m1, m2", text)


if __name__ == "__main__":
    unittest.main()
