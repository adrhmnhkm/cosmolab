import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from cosmolab import backup, config, home, review


def _report(stem, decisions, **extra):
    comments = [{"id": f"k{i + 1}", "paragraph": 1, "severity": review.SARAN, "category": "argumen",
                 "comment": "x", "question": "", "quote": "", "grounded": True, "decision": d}
                for i, d in enumerate(decisions)]
    return {"stem": stem, "title": stem.replace("_", " "), "comments": comments, "paragraphs": [], **extra}


class TestHome(unittest.TestCase):
    def setUp(self):
        self._old = config.ROOT
        self._tmp = tempfile.TemporaryDirectory()
        config._set_root(Path(self._tmp.name) / "data")
        config.ensure_dirs()
        folder = review.reviews_dir()
        folder.mkdir(parents=True, exist_ok=True)
        reports = [
            _report("a_pending", [review.PENDING, review.ACCEPT, review.PENDING]),
            _report("b_ready", [review.ACCEPT, review.DROP]),
            _report("c_sent", [review.ACCEPT], docx_path="x.docx"),
            _report("d_weak", [], similarity={"weak": True},
                    coverage={"items": [{"status": "tidak_tersedia"}, {"status": "diunduh"}]}),
        ]
        for r in reports:
            (folder / f"{r['stem']}.json").write_text(json.dumps(r), encoding="utf-8")

    def tearDown(self):
        config._set_root(self._old)
        self._tmp.cleanup()

    def test_todo(self):
        papers = [{"file": "a.pdf", "thesis": "t"}, {"file": "b.pdf"}, {"file": "c.pdf", "thesis": ""}]
        items = {it["stem"] or it["kind"]: it for it in home.todo(papers)}
        self.assertEqual(items["a_pending"]["detail"], "2 dari 3 komentar belum diputuskan")
        self.assertEqual(items["b_ready"]["detail"], "siap, Word belum dibuat")
        self.assertNotIn("c_sent", items)  # Word made: done
        self.assertEqual(items["d_weak"]["detail"],
                         "pembanding kemiripan lemah; 1 sumber perlu diminta ke mahasiswa; siap, Word belum dibuat")
        self.assertEqual(items["analisis"]["title"], "2 paper belum dianalisis")
        self.assertEqual(home.summary(papers)["reviews"], 4)

    def test_word_made_before_tracking_counts_as_sent(self):
        folder = review.reviews_dir()
        r = _report("e_old", [review.ACCEPT], source="tesis.docx", reviewed_at="2026-11-13T11:24:20")
        (folder / "e_old.json").write_text(json.dumps(r), encoding="utf-8")
        self.assertIn("e_old", [it["stem"] for it in home.todo([])])
        (config.ROOT / "audit.jsonl").write_text(json.dumps(
            {"time": "2026-11-13T12:26:00", "event": "review_draf_kirim", "file": "tesis.docx"}) + "\n", encoding="utf-8")
        self.assertNotIn("e_old", [it["stem"] for it in home.todo([])])

    def test_nothing_waiting(self):
        shutil.rmtree(review.reviews_dir())
        self.assertEqual(home.todo([{"file": "a.pdf", "thesis": "t"}]), [])

    def test_recent_and_describe(self):
        rows = [{"time": "2026-11-13T11:24:20", "event": "review_draf", "file": r"C:\tmp\tesis_adi.docx", "comments": 66},
                {"time": "2026-11-12T09:00:00", "event": "tanya", "question": "Apa itu ateisme digital?"}]
        (config.ROOT / "audit.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\nrusak\n", encoding="utf-8")
        got = home.recent(5)
        self.assertEqual([home.describe(r) for r in got],
                         ["Review draf: tesis_adi.docx, 66 komentar", "Tanya koleksi: Apa itu ateisme digital?"])
        self.assertEqual(home.when(got[0]["time"]), "13 Nov 11:24")

    def test_setup_checks_and_backup_age(self):
        with mock.patch.object(backup, "default_dir", lambda: Path(self._tmp.name) / "backups"):
            checks = {c["label"]: c for c in home.setup_checks()}
            self.assertFalse(checks["Backup"]["ok"])
            self.assertIn("Belum pernah", checks["Backup"]["detail"])

            folder = Path(self._tmp.name) / "backups"
            folder.mkdir()
            z = folder / "data_1.zip"
            z.write_bytes(b"")
            old = datetime(2026, 11, 1).timestamp()
            os.utime(z, (old, old))
            checks = {c["label"]: c for c in home.setup_checks(now=datetime(2026, 11, 13))}
            self.assertFalse(checks["Backup"]["ok"])
            self.assertIn("12 hari lalu", checks["Backup"]["detail"])
            checks = {c["label"]: c for c in home.setup_checks(now=datetime(2026, 11, 3))}
            self.assertTrue(checks["Backup"]["ok"])

    def test_projects_overview(self):
        with mock.patch.object(home._usage, "all_roots", lambda: [("(data utama)", config.ROOT)]):
            rows = home.projects_overview()
        self.assertEqual(rows[0]["Review draf"], 4)
        self.assertEqual(rows[0]["Komentar belum diputuskan"], 2)

    def test_chart_data(self):
        from datetime import date

        papers = [
            {"file": "a", "year": "2025", "thesis": "t", "supports_or_critiques": "supports", "source": "arxiv",
             "faculty": "ekonomi", "created_at": "2026-11-02 10:00:00"},
            {"file": "b", "year": "2019", "thesis": "t", "supports_or_critiques": "critiques", "source": "openalex",
             "faculty": "ekonomi", "created_at": "2026-10-01 10:00:00"},
            {"file": "c", "year": "2022", "thesis": "t", "supports_or_critiques": "supports", "source": "arxiv"},
            {"file": "d", "year": "", "source": "doaj", "created_at": "2026-11-12 08:00:00"},
        ]
        years = home.year_counts(papers, now=datetime(2026, 11, 13))
        self.assertEqual([(r["Tahun"], r["Baru"]) for r in years["rows"]],
                         [("2019", False), ("2022", True), ("2025", True)])
        self.assertAlmostEqual(years["recent_share"], 2 / 3)
        self.assertEqual(years["unknown"], 1)

        papers[0]["argument_type"] = papers[1]["argument_type"] = "empiris_kuantitatif"
        self.assertEqual(home.method_counts(papers), [{"Nama": "Empiris kuantitatif", "Paper": 2},
                                                      {"Nama": "Lainnya", "Paper": 1}])
        self.assertEqual(home.source_counts(papers)[0], {"Nama": "arXiv", "Paper": 2})
        many = home.ranked_counts([f"x{i}" for i in range(8)], top=6)
        self.assertEqual(many[-1], {"Nama": "Lainnya", "Paper": 2})

        k = home.kpis(papers, now=datetime(2026, 11, 13))
        self.assertEqual((k["papers"], k["new_this_month"], k["analyzed"], k["pending"], k["reviews_open"]),
                         (4, 2, 3, 2, 3))
        growth = home.paper_growth(papers, days=3, today=date(2026, 11, 13))
        self.assertEqual(growth, [3, 4, 4])  # one paper has no date and always counts

        (config.ROOT / "audit.jsonl").write_text(
            json.dumps({"time": "2026-11-13T10:00:00", "event": "tanya"}) + "\n"
            + json.dumps({"time": "2026-11-12T10:00:00", "event": "tanya"}) + "\n", encoding="utf-8")
        days = home.activity_days(weeks=2, today=date(2026, 11, 13))  # a Friday
        self.assertEqual(days[0]["Tanggal"], "2026-11-02")             # Monday a week earlier
        self.assertEqual(days[-1]["Tanggal"], "2026-11-13")            # no days after today
        self.assertEqual(sum(d["Kegiatan"] for d in days), 2)
        self.assertEqual(home.weekly_activity(days), [0, 2])

    def test_owner_or_team(self):
        with mock.patch.dict(os.environ, {"COSMOLAB_TEAM_MODE": "1"}):
            self.assertFalse(home.is_owner())
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COSMOLAB_TEAM_MODE", None)
            self.assertTrue(home.is_owner())


if __name__ == "__main__":
    unittest.main()
