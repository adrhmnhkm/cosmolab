import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cosmolab import analyze, matrix


NEW = {"thesis": "t", "research_question": "Apakah literasi keuangan memengaruhi tabungan?",
       "research_method": "Regresi linier berganda", "sample_data": "312 mahasiswa di Yogyakarta, 2024",
       "key_findings": ["Literasi berpengaruh positif", "Gender tidak berpengaruh"],
       "limitations": ["Sampel satu kota"], "future_research": ["Tambah variabel pendapatan orang tua"]}
OLD = {"thesis": "t", "research_method": "Survei", "key_findings": ["x"]}


def _paper(file, raw):
    return {"file": file, "title": f"Paper {file}", "year": "2024", "faculty": "ekonomi", "thesis": raw.get("thesis"),
            "argument_type": "empiris_kuantitatif", "raw_json": json.dumps(raw), "premises_json": "[]"}


class TestLitFields(unittest.TestCase):
    def test_schema_and_prompts(self):
        dumped = analyze.PaperAnalysis(thesis="t").model_dump()
        for key in analyze.LIT_FIELDS:
            self.assertIn(key, dumped)
        for prompt in analyze.PROMPTS.values():
            for key in analyze.LIT_FIELDS:
                self.assertIn(f'"{key}"', prompt)
        self.assertEqual(matrix.LIT_KEYS, analyze.LIT_FIELDS)

    def test_old_analysis_needs_fields(self):
        self.assertTrue(analyze.needs_lit_fields(OLD))
        self.assertFalse(analyze.needs_lit_fields(analyze.PaperAnalysis(**NEW).model_dump()))
        self.assertFalse(analyze.needs_lit_fields({}))  # not analyzed at all is a different list

    def test_matrix_columns_and_exports(self):
        papers = [_paper("a.pdf", NEW), _paper("b.pdf", OLD), {"file": "c.pdf", "title": "Belum", "raw_json": None}]
        with mock.patch.object(matrix.db, "get_all_papers_with_analyses", lambda: papers):
            rows = matrix.build_literature_matrix()
        a, b, c = rows
        self.assertEqual(a["sample"], "312 mahasiswa di Yogyakarta, 2024")
        self.assertEqual(a["findings"], "Literasi berpengaruh positif | Gender tidak berpengaruh")
        self.assertEqual((a["old_analysis"], b["old_analysis"], c["old_analysis"]), (False, True, False))
        self.assertEqual(b["limitations"], "-")

        with tempfile.TemporaryDirectory() as tmp:
            out = matrix.export_matrix_csv(rows, Path(tmp) / "m.csv")
            with open(out, encoding="utf-8-sig", newline="") as f:
                table = list(csv.reader(f))
            self.assertIn("Sampel dan data", table[0])
            self.assertEqual(table[1][table[0].index("Saran riset lanjutan")], "Tambah variabel pendapatan orang tua")
            md = matrix.export_matrix_markdown(rows, Path(tmp) / "m.md").read_text(encoding="utf-8")
            self.assertIn("| Tujuan riset | Metode | Sampel dan data |", md)
            self.assertEqual(len([ln for ln in md.splitlines() if ln.startswith("| ")]), 4)  # header + 3 rows


if __name__ == "__main__":
    unittest.main()
