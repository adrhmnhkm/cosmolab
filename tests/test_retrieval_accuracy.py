"""Passage relevance gate, reranking without refill, and the lighter evaluation run."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cosmolab import config, evaluate, passages, retrieval

PAGES = [
    {"page": 1, "paragraphs": ["The kalam argument claims the universe has a temporal beginning and therefore a cause."]},
    {"page": 2, "paragraphs": ["This section describes the general argument structure used in the literature review."]},
]


class TempRoot(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = config.ROOT
        config._set_root(Path(self._tmp.name))
        passages.clear_cache()

    def tearDown(self):
        passages.clear_cache()
        config._set_root(self._old)
        self._tmp.cleanup()


class PassageGateTests(TempRoot):
    def _search(self, query, extra=""):
        with mock.patch("cosmolab.extract.get_paper_pages", return_value=PAGES):
            return passages.search("x.pdf", query, top_k=5, extra_terms=extra, dense=False)

    def test_one_shared_word_is_not_a_match(self):
        hits = self._search("kalam temporal argument")
        self.assertEqual([h["page"] for h in hits], [1])  # page 2 only shares "argument"

    def test_off_topic_question_finds_nothing(self):
        self.assertEqual(self._search("resep rendang daging sapi"), [])

    def test_expansion_terms_bridge_another_language(self):
        self.assertEqual(self._search("awal mula alam semesta"), [])
        self.assertEqual([h["page"] for h in self._search("awal mula alam semesta", "temporal beginning universe")], [1])


    def test_pdf_ligatures_match_plain_letters(self):
        self.assertEqual(passages.tokenize("an actual ﬁnite ﬂow"), passages.tokenize("an actual finite flow"))

    def test_generic_academic_words_do_not_make_a_match(self):
        pages = [{"page": 1, "paragraphs": ["A time series analysis of bank financing and replacement strategy for small firms."]}]
        with mock.patch("cosmolab.extract.get_paper_pages", return_value=pages):
            got = passages.search("y.pdf", "harga tiket kereta", top_k=5,
                                  extra_terms="time series rail fare replacement strategy", dense=False)
        self.assertEqual(got, [])

    def test_question_of_only_generic_words_still_matches(self):
        pages = [
            {"page": 1, "paragraphs": ["We compare forecasting methods for time series data with ARIMA across many datasets."]},
            {"page": 2, "paragraphs": ["Perbedaan metode yang digunakan dalam penelitian ini dijelaskan pada bagian berikut."]},
        ]
        with mock.patch("cosmolab.extract.get_paper_pages", return_value=pages):
            self.assertEqual([h["page"] for h in passages.search("z.pdf", "time series forecasting", dense=False)], [1])
            # "perbedaan" names no topic: it must not pull in the methods boilerplate on page 2.
            self.assertEqual([h["page"] for h in passages.search("z.pdf", "perbedaan metode time series", dense=False)], [1])

    def test_question_words_do_not_unlock_a_match(self):
        pages = [{"page": 1, "paragraphs": ["Contoh perbedaan yang jelas terlihat pada kelompok kontrol dan perlakuan."]}]
        with mock.patch("cosmolab.extract.get_paper_pages", return_value=pages):
            self.assertEqual(passages.search("w.pdf", "contoh perbedaan zakat produktif", dense=False), [])


class JudgeTests(unittest.TestCase):
    CUT = '{"results": [{"id": 1, "verdict": "didukung", "reason": "a", "evidence": ["E1"]}, {"id": 2, "verdict": "'

    def test_cut_off_reply_keeps_whole_rows(self):
        from cosmolab import entail
        self.assertEqual([r["id"] for r in entail._complete_results(self.CUT)], [1])

    def test_claims_left_out_are_asked_again_one_by_one(self):
        from cosmolab import entail
        calls = []

        def judge(batch, model):
            calls.append([r["id"] for r in batch])
            if len(batch) > 1:
                return {1: {"verdict": "didukung", "reason": "a"}}
            return {batch[0]["id"]: {"verdict": "tidak_didukung", "reason": "b"}}

        claims = [{"id": i, "text": "klaim", "matched": [{"file": "a.pdf"}]} for i in (1, 2, 3)]
        rows = entail._judge_claims(claims, "m", judge, evidence_fn=lambda text, p: [])
        self.assertEqual([r["verdict"] for r in rows], ["didukung", "tidak_didukung", "tidak_didukung"])
        self.assertEqual(calls, [[1, 2, 3], [2], [3]])


class LocalEmbedTests(unittest.TestCase):
    class Fake:
        def __init__(self):
            self.seen = []

        def embed(self, texts, batch_size=None):
            self.seen = list(texts)
            return [[float(len(t))] for t in texts]

    def _embed(self, model, texts, kind):
        fake = self.Fake()
        with mock.patch.object(config, "EMBED_MODEL", model), \
             mock.patch.object(passages, "_local_model", return_value=fake):
            return passages.embed(texts, kind=kind), fake.seen

    def test_bge_m3_gets_no_prefix_and_order_is_kept(self):
        texts = ["panjang sekali teksnya", "a b", "sedang saja"]
        vecs, seen = self._embed("local:BAAI/bge-m3", texts, "query")
        self.assertEqual(sorted(seen, key=len), seen)        # sent shortest first
        self.assertEqual(vecs, [[float(len(t))] for t in texts])  # returned in the caller's order
        self.assertFalse(any(s.startswith(("query: ", "passage: ")) for s in seen))

    def test_e5_keeps_its_prefix(self):
        _, seen = self._embed("local:intfloat/multilingual-e5-large", ["teks"], "query")
        self.assertEqual(seen, ["query: teks"])


class RoundCitationTests(unittest.TestCase):
    def test_author_year_in_round_brackets_is_a_claim(self):
        from cosmolab import entail
        claims = entail.split_claims(
            "Al-Ghazali menolak keharusan sebab-akibat alami (Malik, 2025; Craig, 1979, hlm. 3). "
            "Menurut Hume (1748) kebiasaan membentuk keyakinan sebab-akibat. "
            "Hume menulis *An Enquiry Concerning Human Understanding* (1748) di Skotlandia.",
            include_uncited=False,
        )
        self.assertEqual(len(claims), 2)
        self.assertEqual([c["label"] for c in claims[0]["citations"]], ["Malik", "Craig"])
        self.assertEqual(claims[0]["citations"][1]["page"], "3")
        self.assertEqual(claims[1]["citations"][0]["label"], "Hume")

    def test_square_citations_are_left_alone(self):
        from cosmolab import entail
        claims = entail.split_claims("Kausalitas dan nonlokalitas dijadikan aksioma [Popescu & Rohrlich (1997), Hal. 2].")
        self.assertEqual(claims[0]["citations"][0]["label"], "Popescu & Rohrlich")


class JudgeModelTests(unittest.TestCase):
    def test_claims_are_judged_by_the_judge_model(self):
        from cosmolab import entail
        seen = {}

        class FakeClient:
            def __init__(self, base_url=None, api_key=None):
                seen["url"] = base_url
                self.chat = self
                self.completions = self

            def create(self, model, **kw):
                seen["model"] = model
                msg = mock.Mock(content='{"results": [{"id": 1, "verdict": "didukung", "reason": "r"}]}')
                return mock.Mock(choices=[mock.Mock(message=msg)])

        with mock.patch.object(config, "JUDGE_MODEL", "pemeriksa"),              mock.patch.object(config, "JUDGE_BASE_URL", "http://judge/v1"),              mock.patch("openai.OpenAI", FakeClient):
            entail._llm_judge([{"id": 1, "text": "k", "evidence": []}])
        self.assertEqual(seen, {"url": "http://judge/v1", "model": "pemeriksa"})


class DialecticTriggerTests(unittest.TestCase):
    def test_everyday_words_do_not_start_a_debate(self):
        from cosmolab.ask_agent import _detect_query_intent as intent
        self.assertIsNone(intent("Apa perbedaan metode peramalan dalam waktu singkat?")["argument_type"])
        self.assertFalse(intent("Apa rumusan masalah dan beda kedua model?")["needs_contrast"])
        got = intent("Bagaimana kritik terhadap argumen kalam?")
        self.assertEqual((got["argument_type"], got["needs_contrast"]), ("kalam", True))

class RerankTests(TempRoot):
    CANDS = [{"file": f"p{i}.pdf", "title": f"P{i}", "thesis": "t"} for i in range(1, 7)]

    def _client(self, text):
        client = mock.Mock()
        client.chat.completions.create.return_value = mock.Mock(choices=[mock.Mock(message=mock.Mock(content=text))])
        return client

    def test_rejected_papers_are_not_refilled_and_result_is_cached(self):
        client = self._client("[2]")
        with mock.patch.object(retrieval, "expand_academic_query", return_value=[]), \
             mock.patch.object(retrieval, "_best_passage", return_value="teks asli"), \
             mock.patch.object(config, "LLM_CACHE", True):
            got = retrieval.rerank_papers("q", self.CANDS, top_k=5, client=client, model="m")
            again = retrieval.rerank_papers("q", self.CANDS, top_k=5, client=client, model="m")
        self.assertEqual([c["file"] for c in got], ["p2.pdf"])
        self.assertEqual([c["file"] for c in again], ["p2.pdf"])
        self.assertEqual(client.chat.completions.create.call_count, 1)
        prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("Passage from the paper's own text", prompt)

    def test_empty_list_means_no_source(self):
        with mock.patch.object(retrieval, "expand_academic_query", return_value=[]), \
             mock.patch.object(retrieval, "_best_passage", return_value=""):
            self.assertEqual(retrieval.rerank_papers("q", self.CANDS, top_k=5, client=self._client("[]"), model="m"), [])


class LighterRunTests(TempRoot):
    ITEMS = ([{"id": f"r{i}", "kind": "retrieval", "question": "q", "file": "a.pdf", "pages": [1]} for i in range(4)]
             + [{"id": f"c{i}", "kind": "claim", "claim": "k", "file": "a.pdf", "expected": "didukung"} for i in range(4)])

    def test_limit_progress_and_failed_claims_left_out(self):
        steps = []

        def checks(items, **kw):
            return [{"verdict": "belum_dicek", "reason": "Pemeriksa AI gagal dijalankan: Connection error."}
                    if i == 0 else {"verdict": "didukung", "reason": ""} for i, _ in enumerate(items)]

        with mock.patch.object(evaluate, "_retrieval_hit", return_value={"id": "r", "hit": True, "rank": 1}), \
             mock.patch.object(evaluate, "_sources", return_value=[]), \
             mock.patch("cosmolab.entail.check_claims", side_effect=checks), \
             mock.patch("cosmolab.db.get_all_papers_with_analyses", return_value=[]):
            r = evaluate.run(items=self.ITEMS, limit=2, save=False, progress_cb=steps.append)
        self.assertEqual(r["retrieval"]["n"], 2)
        self.assertEqual(r["negatives"]["n"], 2)
        self.assertEqual((r["claims"]["n"], r["claims"]["failed"], r["claims"]["accuracy"]), (1, 1, 1.0))
        self.assertIn("halaman 1/2", steps)
        self.assertEqual(r["negatives"]["rejected"], 1.0)

    def test_unreachable_ai_is_reported(self):
        with mock.patch.object(config, "LLM_BASE_URL", "http://127.0.0.1:9/v1"):
            self.assertIn("tidak bisa dihubungi", evaluate.ai_reachable(timeout=1))


if __name__ == "__main__":
    unittest.main()
