import tempfile
import unittest
from pathlib import Path

from cosmolab import config, faculties, inspector


class TestClientProjects(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_projects_dir = config.PROJECTS_DIR
        config.PROJECTS_DIR = Path(self._tmp.name)

    def tearDown(self):
        config.PROJECTS_DIR = self._orig_projects_dir
        config.use_project(None)
        self._tmp.cleanup()

    def test_rejects_unsafe_names(self):
        for bad in ("", "Bad Name", "../evil", "a/b", "-start", "x" * 65):
            with self.assertRaises(ValueError, msg=bad):
                config.validate_project_name(bad)
        self.assertEqual(config.validate_project_name(" Klien-A_1 "), "klien-a_1")

    def test_use_project_moves_every_path(self):
        config.create_project("klien-a", client="Klien A")
        config.use_project("klien-a")
        root = Path(self._tmp.name) / "klien-a"
        self.assertEqual(config.PROJECT, "klien-a")
        self.assertEqual(config.ROOT, root)
        for p in (config.PDF_DIR, config.TEXT_DIR, config.ANALYSIS_DIR, config.DB_FILE, config.META_FILE):
            self.assertEqual(p.parent, root)
        self.assertEqual(faculties._custom_faculties_file().parent, root)
        self.assertEqual(inspector._inspector_dir().parent, root)
        self.assertEqual(config.project_info()["client"], "Klien A")

    def test_missing_project_and_duplicates(self):
        with self.assertRaises(FileNotFoundError):
            config.use_project("tidak-ada")
        config.create_project("klien-b")
        with self.assertRaises(FileExistsError):
            config.create_project("klien-b")
        self.assertEqual([p["name"] for p in config.list_projects()], ["klien-b"])

    def test_no_project_uses_default_root(self):
        config.use_project(None)
        self.assertIsNone(config.PROJECT)
        self.assertTrue(config.ROOT.is_absolute())


if __name__ == "__main__":
    unittest.main()
