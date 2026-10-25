import unittest
import tempfile
from pathlib import Path
from cosmolab.harvest import _normalize_title, _title_is_duplicate
from cosmolab.analyze import _strip_references, _trim
from cosmolab import db
from cosmolab import export


class TestCosmolabPipeline(unittest.TestCase):

    def test_title_deduplication(self):
        t1 = "A Mathematician Reads the Kalam Cosmological Argument"
        t2 = "a mathematician reads the kalam cosmological argument."
        t3 = "Cosmological Argument: A Modern Review"

        self.assertTrue(_title_is_duplicate(t2, [t1]))
        self.assertFalse(_title_is_duplicate(t3, [t1]))

    def test_reference_stripping(self):
        text = (
            "Introduction to the kalam argument.\n"
            "Premise 1: Whatever begins to exist has a cause.\n"
            "Conclusion: The universe has a cause.\n"
            "\nReferences\n"
            "1. Craig, W.L. (1979). The Kalam Cosmological Argument.\n"
            "2. Smith, Q. (1993). Atheism and Cosmology.\n"
        )
        cleaned = _strip_references(text)
        self.assertNotIn("Craig, W.L.", cleaned)
        self.assertIn("Premise 1", cleaned)

    def test_trim_sampling(self):
        long_text = "A" * 1000 + "B" * 1000 + "C" * 1000
        trimmed = _trim(long_text, limit=1500)
        self.assertLessEqual(len(trimmed), 1600)
        self.assertIn("[... sections omitted for length ...]", trimmed)

    def test_database_and_search(self):
        stats = db.sync_all()
        self.assertIn("papers_synced", stats)

        results = db.search("kalam", limit=3)
        self.assertIsInstance(results, list)
        if results:
            self.assertIn("title", results[0])

    def test_bibtex_export(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            bib_file = Path(tmp_dir) / "test.bib"
            res = export.export_bibtex(out_path=bib_file)
            self.assertTrue(res.exists())
            self.assertIn("@article", res.read_text(encoding="utf-8"))

    def test_obsidian_export(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault_dir = Path(tmp_dir) / "vault"
            res = export.export_obsidian(vault_dir=vault_dir)
            self.assertTrue(res.exists())
            self.assertTrue((res / "_Index.md").exists())


if __name__ == "__main__":
    unittest.main()
