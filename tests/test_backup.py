import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from cosmolab import backup, config, db


class TestBackup(unittest.TestCase):
    def setUp(self):
        self._old = config.ROOT
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name) / "data"
        config._set_root(root)
        config.ensure_dirs()
        db.init_db()
        (config.PDF_DIR / "a.pdf").write_bytes(b"%PDF-1.4")
        (config.TEXT_DIR / "a.txt").write_text("teks", encoding="utf-8")
        (root / "cache").mkdir()
        (root / "cache" / "llm.json").write_text("{}", encoding="utf-8")
        self.out = Path(self._tmp.name) / "backups"

    def tearDown(self):
        config._set_root(self._old)
        self._tmp.cleanup()

    def _names(self, res):
        with zipfile.ZipFile(res["path"]) as zf:
            return set(zf.namelist())

    def test_full_backup_has_consistent_db_and_skips_cache(self):
        res = backup.make_backup(self.out)
        names = self._names(res)
        self.assertIn("data/pdf/a.pdf", names)
        self.assertIn("data/text/a.txt", names)
        self.assertIn("data/cosmolab.db", names)
        self.assertNotIn("data/cache/llm.json", names)
        self.assertFalse(any(n.endswith(("-wal", "-shm")) for n in names))

        with zipfile.ZipFile(res["path"]) as zf:
            zf.extract("data/cosmolab.db", self._tmp.name + "/x")
        con = sqlite3.connect(Path(self._tmp.name) / "x" / "data" / "cosmolab.db")
        tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        con.close()
        self.assertIn("papers", tables)

    def test_options(self):
        names = self._names(backup.make_backup(self.out, include_pdf=False, include_cache=True))
        self.assertNotIn("data/pdf/a.pdf", names)
        self.assertIn("data/cache/llm.json", names)

    def test_out_dir_inside_root_is_not_zipped_into_itself(self):
        inner = config.ROOT / "backups"
        backup.make_backup(inner)
        names = self._names(backup.make_backup(inner))
        self.assertFalse(any(n.startswith("data/backups/") for n in names))


if __name__ == "__main__":
    unittest.main()
