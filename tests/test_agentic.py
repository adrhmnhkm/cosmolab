import unittest
import tempfile
from pathlib import Path
from cosmolab import db
from cosmolab import export
from cosmolab.ask_agent import _detect_query_intent
from _markers import needs_corpus, needs_network


class TestAgenticSecondBrain(unittest.TestCase):

    def test_intent_detection(self):
        # Test Kalam intent
        intent_kalam = _detect_query_intent("Bagaimana para peneliti membantah klaim Kalam?")
        self.assertEqual(intent_kalam["argument_type"], "kalam")
        self.assertTrue(intent_kalam["needs_contrast"])

        # Test Fine-tuning intent
        intent_ft = _detect_query_intent("Apa bukti penyetelan konstanta alam?")
        self.assertEqual(intent_ft["argument_type"], "fine-tuning")

        # Test Neutral intent
        intent_neutral = _detect_query_intent("Jelaskan konsep kosmologi ini")
        self.assertFalse(intent_neutral["needs_contrast"])

    @needs_corpus
    def test_dialectical_db_queries(self):
        # Test dialectical pairs retrieval
        pairs = db.get_dialectical_pairs(argument_type="kalam")
        self.assertIn("proponents", pairs)
        self.assertIn("opponents", pairs)
        self.assertIn("evaluators", pairs)

        # Test paper knowledge summary
        all_papers = db.get_all_papers_with_analyses()
        if all_papers:
            sample_file = all_papers[0]["file"]
            summary = db.get_paper_knowledge_summary(sample_file)
            self.assertIsNotNone(summary)
            self.assertIn("thesis", summary)

    def test_export_synthesis_to_obsidian(self):
        q = "Bagaimana rekonsiliasi kuantum dan kausalitas?"
        ans = "Peneliti menunjukkan bahwa nonlokalitas tetap menghormati kausalitas relativistik."
        papers = [{"file": "test_paper.pdf", "title": "Test Title", "year": "2025", "supports_or_critiques": "supports"}]
        
        path = export.export_agent_synthesis_to_obsidian(q, ans, papers)
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8")
        self.assertIn("[[test_paper]]", content)
        self.assertIn("Sintesis Riset Dialektis", content)
        path.unlink(missing_ok=True)

    @needs_corpus
    def test_learning_roadmap(self):
        from cosmolab.curriculum import get_learning_roadmap
        levels = get_learning_roadmap()
        self.assertEqual(len(levels), 4)
        for lvl in levels:
            self.assertIn("level", lvl)
            self.assertIn("title", lvl)
            self.assertIn("papers", lvl)

    @needs_corpus
    def test_export_flashcards(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fc_path = export.export_flashcards_to_obsidian(vault_dir=Path(tmp_dir))
            self.assertTrue(fc_path.exists())
            text = fc_path.read_text(encoding="utf-8")
            self.assertIn("#flashcard", text)

    def test_socratic_dilemmas(self):
        from cosmolab.sparring import SOCRATIC_DILEMMAS
        self.assertGreaterEqual(len(SOCRATIC_DILEMMAS), 3)
        for d in SOCRATIC_DILEMMAS:
            self.assertIn("topic", d)
            self.assertIn("dilemma", d)

    @needs_network
    def test_unpaywall_resolver(self):
        from cosmolab.harvest import _resolve_unpaywall
        # Test with known open-access DOI
        pdf_url = _resolve_unpaywall("10.24204/ejpr.v9i2.1938")
        self.assertIsNotNone(pdf_url)
        self.assertTrue(pdf_url.startswith("http"))


if __name__ == "__main__":
    unittest.main()
