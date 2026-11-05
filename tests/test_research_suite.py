import unittest
from pathlib import Path
import tempfile
from cosmolab import citations, matrix, gap_finder, db


class TestResearchSuite(unittest.TestCase):

    def test_citation_formatting(self):
        sample_paper = {
            "title": "A Mathematician Reads the Kalam Cosmological Argument",
            "year": 2022,
            "doi": "10.1007/s00283-022-10224-8",
            "url": "https://arxiv.org/pdf/2207.06165"
        }
        apa = citations.format_apa(sample_paper)
        self.assertIn("2022", apa)
        self.assertIn("Mathematician", apa)

        chicago_bib = citations.format_chicago_bib(sample_paper)
        self.assertIn("2022", chicago_bib)

        in_text = citations.format_in_text_apa(sample_paper)
        self.assertTrue(in_text.startswith("(") and in_text.endswith(")"))

    def test_ris_export(self):
        papers = db.get_all_papers_with_analyses()[:3]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_ris = Path(tmpdir) / "test.ris"
            res = citations.export_ris(papers, out_ris)
            self.assertTrue(res.exists())
            text = res.read_text(encoding="utf-8")
            self.assertIn("TY  - JOUR", text)
            self.assertIn("ER  -", text)

    def test_matrix_builder_and_exports(self):
        mat = matrix.build_literature_matrix(faculty_id="all")
        self.assertIsInstance(mat, list)
        self.assertGreater(len(mat), 0)

        with tempfile.TemporaryDirectory() as tmpdir:
            # CSV export
            out_csv = Path(tmpdir) / "test_matrix.csv"
            matrix.export_matrix_csv(mat, out_csv)
            self.assertTrue(out_csv.exists())
            self.assertGreater(out_csv.stat().st_size, 100)

            # Markdown export
            out_md = Path(tmpdir) / "test_matrix.md"
            matrix.export_matrix_markdown(mat, out_md)
            self.assertTrue(out_md.exists())
            md_text = out_md.read_text(encoding="utf-8")
            self.assertIn("Matriks Sintesis Literatur", md_text)
            self.assertIn("| No |", md_text)

        # Recency compliance audit test
        rec = matrix.calculate_recency_compliance(mat, threshold_years=5)
        self.assertIn("percentage", rec)
        self.assertIn("status_label", rec)
        self.assertIsInstance(rec["percentage"], float)

    def test_gap_finder_save(self):
        mock_data = {
            "faculty_domain": "Ilāhiyyāt",
            "faculty_id": "ilahiyyat",
            "model_used": "test-mock",
            "executive_summary": "Kondisi riset kosmologi saat ini terbelah.",
            "established_consensus": ["Alam semesta memiliki ekspansi."],
            "unresolved_tensions": [{
                "issue": "Singularitas",
                "thesis_side": "Ada titik awal",
                "antithesis_side": "Vakum kuantum",
                "why_stuck": "Ketidakpastian teori gravitasi kuantum"
            }],
            "methodological_blindspots": ["Kurangnya analisis formal."],
            "novel_research_proposals": [{
                "title": "Rekonstruksi Kausalitas Kuantum dalam Kalam Kontemporer",
                "target_level": "Disertasi S3",
                "gap_addressed": "Ketidaksesuaian definisi sebab di level subatomik",
                "research_questions": ["Apakah probabilitas membatalkan keniscayaan?"],
                "proposed_hypothesis": "Probabilitas adalah modus keteraturan 'Adatullah.",
                "theoretical_framework": "Asy'ariyah dan Interpretasi Bohmian",
                "expected_novelty": "Pertemuan pertama ontologi Asy'ariyah dengan mekanika Bohm"
            }]
        }
        res = gap_finder.save_gap_report(mock_data)
        self.assertTrue(res["md_path"].exists())
        self.assertTrue(res["json_path"].exists())
        self.assertIn("Bohmian", res["markdown_content"])


if __name__ == "__main__":
    unittest.main()
