"""The step recorder behind `cosmolab jejak`: off by default, complete when on."""

import io
import unittest
from unittest import mock

from rich.console import Console

from cosmolab import config, db, passages, retrieval, trace, trace_view
from tests.test_retrieval_accuracy import PAGES, TempRoot

DOCS = [{"file": f"p{i}.pdf", "title": f"Paper {i}", "year": 2020 + i, "thesis": "t"} for i in (1, 2, 3)]


def fake_client():
    """One mock client for every LLM call: expansion gets terms, paper rerank picks candidate 1."""
    def create(model, messages, **kw):
        text = messages[-1]["content"]
        content = '["temporal beginning"]' if "search terms" in text else "[1]"
        return mock.Mock(choices=[mock.Mock(message=mock.Mock(content=content))])

    client = mock.Mock()
    client.chat.completions.create.side_effect = create
    return client


class TraceTests(TempRoot):
    def test_off_by_default_and_results_unchanged(self):
        with mock.patch("cosmolab.extract.get_paper_pages", return_value=PAGES):
            plain = passages.search("x.pdf", "kalam temporal argument", dense=False)
            self.assertIsNone(trace._EVENTS)
            trace.add("passages", file="x.pdf")  # no recording: nothing happens
            self.assertIsNone(trace._EVENTS)
            with trace.recording() as events:
                traced = passages.search("x.pdf", "kalam temporal argument", dense=False)
        self.assertEqual(plain, traced)
        self.assertIsNone(trace._EVENTS)
        p = events[0]
        self.assertEqual((p["stage"], p["file"], p["chunks"], p["passed"]), ("passages", "x.pdf", 2, 1))
        self.assertEqual(p["reasons"], {"kata pertanyaan": 1})
        self.assertEqual([h["page"] for h in p["top"]], [1])

    def test_select_sources_records_every_step_in_order(self):
        client = fake_client()
        with mock.patch.object(retrieval.db, "search", side_effect=lambda q, limit=10: list(DOCS)), \
             mock.patch.object(retrieval, "OpenAI", return_value=client), \
             mock.patch("cosmolab.extract.get_paper_pages", return_value=PAGES), \
             mock.patch.object(config, "LLM_CACHE", False), \
             mock.patch.object(config, "RERANK_PASSAGES", False):
            with trace.recording() as events:
                papers, _ = retrieval.select_sources("kalam temporal argument", top_k=2, model="m")

        stages = [e["stage"] for e in events]
        for a, b in (("expand", "rrf"), ("rrf", "rerank_papers"), ("rerank_papers", "select")):
            self.assertLess(stages.index(a), stages.index(b))
        rr = next(e for e in events if e["stage"] == "rerank_papers")
        self.assertEqual((rr["source"], rr["chosen"], rr["rejected"]), ("ai", ["p1.pdf"], ["p2.pdf", "p3.pdf"]))
        rrf = next(e for e in events if e["stage"] == "rrf")
        self.assertEqual([r["file"] for r in rrf["rows"]], ["p1.pdf", "p2.pdf", "p3.pdf"])
        sel = next(e for e in events if e["stage"] == "select")
        self.assertEqual(sel["kept"], [p["file"] for p in papers])
        self.assertEqual(sel["kept"], ["p1.pdf"])
        # Passage search of the chosen paper runs in a worker thread and is still recorded.
        after = [e for e in events[stages.index("rerank_papers"):] if e["stage"] == "passages"]
        self.assertEqual([e["file"] for e in after], ["p1.pdf"])
        self.assertNotEqual(after[0]["thread"], "MainThread")

        out = io.StringIO()
        trace_view.render(events, "kalam temporal argument", console=Console(file=out, width=140))
        text = out.getvalue()
        for part in ("1. Pertanyaan", "4. Gabung", "5. AI memilih", "6. Di dalam", "7. Sumber", "Paper 1", "dipilih #1"):
            self.assertIn(part, text)

    def test_passage_rerank_reason_is_recorded(self):
        hits = [{"page": 1, "text": "a", "bm25": 5.0, "dense": None}, {"page": 2, "text": "b", "bm25": 1.0, "dense": None}]
        with trace.recording() as events:
            passages.rerank("q", list(hits), file_name="x.pdf")
            passages.rerank("q", list(hits), file_name="x.pdf", ranker=lambda q, t, m: [1])
        self.assertEqual(events[0]["source"], "dilewati")
        self.assertEqual((events[1]["source"], events[1]["chosen"], events[1]["rejected"]), ("ai", [2], [1]))

    def test_database_search_records_query_and_weights(self):
        with trace.recording() as events:
            db.search("kalam argumen")
        fts = events[-1]
        self.assertEqual(fts["stage"], "fts")
        self.assertIn('"kalam"*', fts["fts_query"])
        self.assertEqual(fts["weights"]["title"], 10.0)


if __name__ == "__main__":
    unittest.main()
