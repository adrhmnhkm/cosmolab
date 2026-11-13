"""Answers stay inside the collection: no filler papers, no guessed analysis, no hidden model switch."""

import unittest
from unittest import mock

from cosmolab import ask, ask_agent, entail, inspector

NOT_FOUND = "Tidak ditemukan di korpus ini untuk pertanyaan tersebut."


def _summary(file):
    return {"file": file, "title": f"Judul {file}", "year": "2024", "thesis": "inti", "authors": "[]"}


def _passage(file, fallback=False):
    psg = {"file": file, "page": 1, "page_label": "Halaman 1", "verbatim": f"teks {file}"}
    if fallback:
        psg["fallback"] = True
    return psg


class _Resp:
    def __init__(self, text):
        self.choices = [mock.Mock(message=mock.Mock(content=text, reasoning_content=None, reasoning=None))]


class TestAgenticGrounding(unittest.TestCase):
    def _run(self, found, llm=None):
        client = mock.Mock()
        if llm is not None:
            client.chat.completions.create.side_effect = llm
        with mock.patch.object(ask_agent.retrieval, "hybrid_search", return_value=[{"file": "a.pdf"}, {"file": "b.pdf"}]), \
             mock.patch.object(ask_agent.retrieval, "rerank_papers", side_effect=lambda q, c, **kw: c), \
             mock.patch.object(ask_agent.db, "get_paper_knowledge_summary", side_effect=_summary), \
             mock.patch.object(ask_agent.db, "get_dialectical_pairs") as pairs, \
             mock.patch.object(ask_agent.retrieval, "grounded_passages_batch", return_value=found), \
             mock.patch.object(ask_agent, "OpenAI", lambda **kw: client):
            res = ask_agent.ask_agentic("Apa pengaruh X terhadap Y?", model="m")
        return res, client, pairs

    def test_papers_without_a_matching_passage_are_left_out(self):
        found = {"a.pdf": [_passage("a.pdf")], "b.pdf": [_passage("b.pdf", fallback=True)]}
        res, client, pairs = self._run(found, llm=lambda **kw: _Resp("Jawaban [Judul a.pdf (2024)]."))
        self.assertEqual([p["file"] for p in res["referenced_papers"]], ["a.pdf"])
        sent = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        self.assertNotIn("b.pdf", sent)
        self.assertNotIn("Terverifikasi", sent)
        pairs.assert_not_called()  # no contrast asked: no extra papers from the other side

    def test_no_match_answers_not_found_without_calling_the_ai(self):
        found = {"a.pdf": [_passage("a.pdf", fallback=True)], "b.pdf": []}
        res, client, _ = self._run(found)
        self.assertEqual(res["answer"], NOT_FOUND)
        self.assertEqual(res["referenced_papers"], [])
        client.chat.completions.create.assert_not_called()

    def test_failure_does_not_switch_to_another_model(self):
        def boom(**kw):
            raise RuntimeError("kuota habis")

        res, client, _ = self._run({"a.pdf": [_passage("a.pdf")], "b.pdf": []}, llm=boom)
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertIn("kuota habis", res["answer"])
        self.assertIn("model m", res["answer"])

    def test_prompt_no_longer_allows_outside_knowledge(self):
        self.assertNotIn("penalaran akademik", ask_agent.AGENTIC_SYSTEM_PROMPT)
        self.assertIn("Catatan analis:", ask_agent.AGENTIC_SYSTEM_PROMPT)


class TestClassicGrounding(unittest.TestCase):
    def test_no_candidates_answers_not_found(self):
        with mock.patch.object(ask.retrieval, "hybrid_search", return_value=[]), \
             mock.patch.object(ask, "OpenAI") as client:
            self.assertEqual(ask.ask("Apa pengaruh X?", model="m"), NOT_FOUND)
        client.assert_not_called()


class TestEntailEvidence(unittest.TestCase):
    def test_fallback_passage_is_not_evidence(self):
        paper = {"file": "a.pdf", "title": "A", "thesis": "tesis AI", "conclusion": "kesimpulan AI"}
        with mock.patch("cosmolab.retrieval.find_grounded_passages", return_value=[_passage("a.pdf", fallback=True)]):
            self.assertEqual(entail.gather_evidence("klaim", paper, use_analysis=False), [])

    def test_check_answer_judges_against_paper_text_only(self):
        with mock.patch.object(entail, "_judge_claims", return_value=[]) as judge:
            entail.check_answer("Klaim [A (2024)].", papers=[], judge=lambda *a: {}, evidence_fn=lambda *a: [])
        self.assertIs(judge.call_args.kwargs.get("use_analysis"), False)


class TestInspectWithoutAbstract(unittest.TestCase):
    META = {"title": "Judul", "authors": ["A"], "year": "2024", "venue": "Jurnal", "publisher": "P", "doi": "10.1/x",
            "citation_count": 0, "is_oa": False, "pdf_url": None, "url": "https://doi.org/10.1/x", "abstract": None}

    def test_no_abstract_no_ai_analysis(self):
        with mock.patch.object(inspector, "fetch_doi_metadata", return_value=dict(self.META)), \
             mock.patch.object(inspector, "OpenAI") as client:
            res = inspector.inspect_paper("10.1/x", model="m")
        client.return_value.chat.completions.create.assert_not_called()
        self.assertTrue(res["success"])
        self.assertEqual(res["analysis"], {})
        self.assertIn("Abstrak tidak tersedia", res["analysis_note"])

    def test_failed_analysis_has_no_stand_in_text(self):
        meta = {**self.META, "abstract": "Abstrak asli."}
        with mock.patch.object(inspector, "fetch_doi_metadata", return_value=meta), \
             mock.patch.object(inspector, "OpenAI") as client:
            client.return_value.chat.completions.create.return_value = _Resp("bukan json")
            res = inspector.inspect_paper("10.1/x", model="m")
        self.assertEqual(res["analysis"], {})
        self.assertIn("Analisis AI gagal", res["analysis_note"])


if __name__ == "__main__":
    unittest.main()
