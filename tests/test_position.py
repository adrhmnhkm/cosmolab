import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cosmolab import config, position


def _papers(n):
    return [{"file": f"p{i}.pdf", "title": f"Paper {i}", "year": "2024", "thesis": "inti",
             "raw_json": json.dumps({"key_findings": [f"temuan {i}"], "research_method": f"kuasi {i}"})} for i in range(1, n + 1)]


class TestPosition(unittest.TestCase):
    def setUp(self):
        self._old = config.ROOT
        self._tmp = tempfile.TemporaryDirectory()
        config._set_root(Path(self._tmp.name) / "data")
        config.ensure_dirs()

    def tearDown(self):
        config._set_root(self._old)
        self._tmp.cleanup()

    def test_question_saved_and_key_follows_question(self):
        self.assertEqual(position.load_question()["question"], "")
        q = position.save_question(" Literasi keuangan ", "Apakah literasi memengaruhi tabungan?", "Berpengaruh positif.")
        self.assertEqual(position.load_question()["topic"], "Literasi keuangan")
        same = {**q, "topic": "lain", "question": "apakah  literasi memengaruhi tabungan?"}
        self.assertEqual(position.question_key(q), position.question_key(same))  # topic, case, spaces do not count
        self.assertNotEqual(position.question_key(q), position.question_key({**q, "hypothesis": "Tidak berpengaruh."}))

    def test_judge_in_batches_and_counts(self):
        papers = _papers(10) + [{"file": "belum.pdf", "title": "Belum dianalisis"}]
        self.assertEqual(position.judge(papers)["error"], "Pertanyaan riset belum diisi.")
        position.save_question("", "Apakah X memengaruhi Y?")
        self.assertEqual(len(position.pending(papers)), 10)  # only analysed papers

        calls = []

        def fake_ask(q, batch, model):
            calls.append(len(batch))
            kinds = [position.SUPPORTS, position.CONTRADICTS, position.UNRELATED]
            return {p["file"]: {"position": kinds[i % 3], "evidence": position.CONTROLLED, "reason": "karena temuan"}
                    for i, p in enumerate(batch)}

        with mock.patch.object(position, "_ask", fake_ask):
            res = position.judge(papers)
        self.assertEqual(calls, [8, 2])
        self.assertEqual(res, {"judged": 10, "failed": 0, "error": None})
        self.assertEqual(position.pending(papers), [])
        self.assertEqual(position.position_of("p1.pdf")["position"], position.SUPPORTS)
        self.assertEqual(position.counts(papers), [{"Posisi": "Mendukung", "Paper": 4},
                                                   {"Posisi": "Menolak", "Paper": 4},
                                                   {"Posisi": "Tidak berkaitan", "Paper": 2}])

        # A new hypothesis makes the old positions stale.
        position.save_question("", "Apakah X memengaruhi Y?", "X menurunkan Y.")
        self.assertEqual(position.load_positions(), {})
        self.assertEqual(len(position.pending(papers)), 10)

    def test_failed_call_keeps_saved_batches(self):
        papers = _papers(10)
        position.save_question("", "Apakah X memengaruhi Y?")
        state = {"n": 0}

        def flaky(q, batch, model):
            state["n"] += 1
            if state["n"] == 2:
                raise RuntimeError("kuota habis")
            return {p["file"]: {"position": position.MIXED, "evidence": "", "reason": "r"} for p in batch}

        with mock.patch.object(position, "_ask", flaky):
            res = position.judge(papers)
        self.assertEqual((res["judged"], res["failed"], res["error"]), (8, 2, "kuota habis"))
        self.assertEqual(len(position.pending(papers)), 2)

    def test_parse_and_bad_answers(self):
        text = '```json\n{"results": [{"id": 1, "position": "mendukung", "evidence": "hubungan", "reason": "a"}, ' \
               '{"id": 9, "position": "menolak"},' \
               ' {"id": 2, "position": "setuju"}, "rusak"]}\n```'
        self.assertEqual(len(position._parse(text)), 3)
        self.assertEqual(position._parse("maaf, tidak bisa"), [])

        class _Resp:
            choices = [mock.Mock(message=mock.Mock(content=text))]

        client = mock.Mock()
        client.chat.completions.create.return_value = _Resp()
        with mock.patch.object(position, "OpenAI", lambda **kw: client):
            got = position._ask({"topic": "", "question": "q", "hypothesis": ""}, _papers(2), "m")
        self.assertEqual(got, {"p1.pdf": {"position": "mendukung", "evidence": "hubungan", "reason": "a"}})
        sent = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("PERTANYAAN RISET: q", sent)
        self.assertIn("Temuan: temuan 2", sent)
        self.assertIn("Metode: kuasi 2", sent)

    def _judge(self, papers, positions, evidence):
        def fake_ask(q, batch, model):
            return {p["file"]: {"position": positions[i], "evidence": evidence[i], "reason": "r"}
                    for i, p in enumerate(batch)}

        with mock.patch.object(position, "_ask", fake_ask):
            position.judge(papers)

    def test_evidence_groups_and_old_positions_judged_again(self):
        papers = _papers(6)
        position.save_question("", "Apakah X memengaruhi Y?", "X meningkatkan Y.")
        self._judge(papers, [position.SUPPORTS] * 4 + [position.MIXED, position.UNRELATED],
                    [position.CONTROLLED, position.CONTROLLED, position.QUALITATIVE, position.ASSOCIATION, "",
                     position.CONTROLLED])
        self.assertEqual(position.pending(papers), [])  # "" (no evidence given) is not asked again
        g = position.evidence_groups(papers)
        self.assertEqual([(t["key"], [p["file"] for p in t["papers"]]) for t in g["tiers"]], [
            ("kuat", ["p1.pdf", "p2.pdf"]),  # p6 is unrelated: left out
            ("pendukung", ["p4.pdf"]),
            ("konteks", ["p3.pdf"]),
            ("lain", ["p5.pdf"]),
        ])
        self.assertEqual(g["tiers"][1]["papers"][0]["note"], "hubungan")
        self.assertEqual((g["judged"], g["effect_study"], g["no_counter"]), (5, True, False))  # p5 is mixed

        # Positions saved before evidence existed are judged again.
        data = json.loads((config.ROOT / position.POSITIONS_FILE).read_text(encoding="utf-8"))
        del data["papers"]["p1.pdf"]["evidence"]
        (config.ROOT / position.POSITIONS_FILE).write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual([p["file"] for p in position.pending(papers)], ["p1.pdf"])

    def test_evidence_groups_for_a_conceptual_collection(self):
        papers = _papers(2)
        position.save_question("", "Bagaimana kedudukan hukum X?")
        self._judge(papers, [position.SUPPORTS, position.SUPPORTS], [position.CONCEPTUAL, position.REVIEW])
        g = position.evidence_groups(papers)
        self.assertEqual([t["key"] for t in g["tiers"]], ["tinjauan", "konteks"])
        self.assertEqual((g["effect_study"], g["no_counter"]), (False, True))
        self.assertEqual(position.evidence_groups([]), {"tiers": [], "judged": 0, "effect_study": False,
                                                        "no_counter": False})

    def test_estimate_text(self):
        self.assertEqual(position.estimate_text(35), "35 paper, 5 panggilan AI, perkiraan 1–3 menit.")
        self.assertEqual(position.estimate_text(3), "3 paper, 1 panggilan AI, perkiraan 10–30 detik.")


if __name__ == "__main__":
    unittest.main()
