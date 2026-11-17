import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cosmolab import config, entail, synthesize


class _Resp:
    def __init__(self, content: str):
        self.choices = [mock.Mock(message=mock.Mock(content=content))]


class TestSynthesize(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.analysis_dir = self.root / "analysis"
        self.synth_dir = self.root / "synthesis"
        self.analysis_dir.mkdir(parents=True)
        self.synth_dir.mkdir(parents=True)

    def tearDown(self):
        self.td.cleanup()

    def _sample_analysis(self, name: str = "paper1"):
        return {
            "_meta": {
                "file": f"{name}.pdf",
                "title": f"Judul Riset {name}",
                "year": "2024",
                "authors": '["Peneliti A"]',
            },
            "argument_type": "empiris_kuantitatif",
            "research_question": "Bagaimana pengaruh X?",
            "research_method": "Regresi Berganda",
            "sample_data": "100 UMKM",
            "key_findings": ["X berpengaruh positif"],
            "limitations": ["Sampel lokal"],
            "future_research": ["Perluas sampel"],
            "supports_or_critiques": "supports",
            "thesis": "X berpengaruh pada Y.",
            "conclusion": "X signifikan terhadap Y.",
            "premises": ["Premis 1"],
            "key_objection": None,
            "key_defense": None,
            "quotes": [
                {"text": "Data membuktikan pengaruh signifikan sebesar 80%.", "page": 4, "page_hint": "Hasil"}
            ],
        }

    def test_synthesize_includes_verbatim_passages_and_checks_claims(self):
        # Write 2 analyses
        p1 = self.analysis_dir / "paper1.json"
        p1.write_text(json.dumps(self._sample_analysis("paper1")), encoding="utf-8")
        p2 = self.analysis_dir / "paper2.json"
        p2.write_text(json.dumps(self._sample_analysis("paper2")), encoding="utf-8")

        sent_payloads = []

        def fake_create(model, messages, **kw):
            user_msg = messages[1]["content"]
            sent_payloads.append(json.loads(user_msg))
            return _Resp(
                "## 1. Peta Posisi\n"
                "Semua paper mendukung [Judul Riset paper1 (2024), Hal. 4].\n"
                "Catatan analis: Sintesis ini menunjukkan konsistensi metodologis."
            )

        mock_client = mock.Mock()
        mock_client.chat.completions.create.side_effect = fake_create

        fake_judge = lambda items, m: {1: {"verdict": "didukung", "reason": "cocok", "evidence": ["E1"]}}
        fake_evidence = lambda claim, paper: [{"paper": paper["title"], "page_label": "Hal. 4", "text": "bukti"}]

        with mock.patch.object(config, "ANALYSIS_DIR", self.analysis_dir), \
             mock.patch.object(config, "SYNTH_DIR", self.synth_dir), \
             mock.patch.object(synthesize, "OpenAI", return_value=mock_client):
            res = synthesize.synthesize(
                model="test-model",
                lang="id",
                check_claims=True,
                judge=fake_judge,
                evidence_fn=fake_evidence,
            )

        self.assertEqual(res["n"], 2)
        self.assertEqual(res["lang"], "id")
        self.assertIn("claims_report", res)
        self.assertEqual(res["claims_total"], 1)
        self.assertEqual(res["claims_flagged"], 0)

        # Check payload contains verbatim passages
        self.assertEqual(len(sent_payloads), 1)
        items = sent_payloads[0]
        self.assertEqual(len(items), 2)
        self.assertIn("verbatim_passages", items[0])
        self.assertEqual(len(items[0]["verbatim_passages"]), 1)
        self.assertEqual(items[0]["verbatim_passages"][0]["page"], 4)
        self.assertIn("80%", items[0]["verbatim_passages"][0]["verbatim"])

        # Check written report file contains report body and audit section
        report_path = Path(res["report"])
        self.assertTrue(report_path.exists())
        content = report_path.read_text(encoding="utf-8")
        self.assertIn("Judul Riset paper1", content)
        self.assertIn("Pemeriksaan Klaim (Audit Akurasi)", content)
        self.assertIn("Didukung sumber", content)

    def test_synthesize_no_analyses_returns_error(self):
        with mock.patch.object(config, "ANALYSIS_DIR", self.analysis_dir), \
             mock.patch.object(synthesize, "OpenAI") as mock_client:
            res = synthesize.synthesize()
        self.assertIn("error", res)
        mock_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
