import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cosmolab import config, usage


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_record_and_load(self):
        usage.record("m1", 100, 50, feature="writer", root=self.root)
        usage.record("m2", 10, 5, feature="ask", root=self.root)
        rows = usage.load(self.root)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["feature"], "writer")
        self.assertEqual(rows[0]["prompt_tokens"], 100)
        self.assertEqual(usage.load(self.root, month="1999-01"), [])

    def test_load_skips_bad_lines(self):
        (self.root / usage.USAGE_FILE).write_text('not json\n{"ts": "2026-11-05", "model": "m"}\n', encoding="utf-8")
        self.assertEqual(len(usage.load(self.root)), 1)

    def test_pricing_cost_and_summary(self):
        with mock.patch.dict(config.env_config, {"COSMOLAB_PRICING": "m1:1000:2000; bad ; m2:x:y"}):
            prices = usage.pricing()
            self.assertEqual(prices, {"m1": (1000.0, 2000.0)})
            entry = {"model": "m1", "prompt_tokens": 1_000_000, "completion_tokens": 500_000}
            self.assertAlmostEqual(usage.cost(entry, prices), 2000.0)
            self.assertIsNone(usage.cost({"model": "m2", "prompt_tokens": 1, "completion_tokens": 1}, prices))

            rows = [
                {"ts": "2026-11-01", "feature": "writer", "model": "m1", "prompt_tokens": 1_000_000, "completion_tokens": 0},
                {"ts": "2026-11-02", "feature": "writer", "model": "m2", "prompt_tokens": 10, "completion_tokens": 0},
                {"ts": "2026-10-02", "feature": "ask", "model": "m1", "prompt_tokens": 5, "completion_tokens": 0},
            ]
            by_feature = {g["key"]: g for g in usage.summarize(rows, by="feature")}
            self.assertEqual(by_feature["writer"]["calls"], 2)
            self.assertEqual(by_feature["writer"]["unpriced"], 1)
            self.assertAlmostEqual(by_feature["writer"]["cost"], 1000.0)
            by_month = {g["key"] for g in usage.summarize(rows, by="month")}
            self.assertEqual(by_month, {"2026-11", "2026-10"})

    def test_format_money(self):
        with mock.patch.dict(config.env_config, {"COSMOLAB_PRICING_CURRENCY": "IDR"}):
            self.assertEqual(usage.format_money(1234567.4), "Rp 1.234.567")
        with mock.patch.dict(config.env_config, {"COSMOLAB_PRICING_CURRENCY": "USD"}):
            self.assertEqual(usage.format_money(1.5), "USD 1.50")

    def test_install_wraps_create_and_logs(self):
        from openai.resources.chat.completions import Completions

        fake = SimpleNamespace(model="m-fake", usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3))
        with mock.patch.object(Completions, "create", lambda self, *a, **k: fake), \
             mock.patch.object(usage, "_installed", False), \
             mock.patch.object(usage, "record") as rec:
            usage.install()
            usage.install()  # second call must not wrap twice
            result = Completions.create(None, model="m-fake", messages=[])
        self.assertIs(result, fake)
        rec.assert_called_once()
        self.assertEqual(rec.call_args.kwargs["model"], "m-fake")
        self.assertEqual(rec.call_args.kwargs["prompt_tokens"], 7)
        self.assertEqual(rec.call_args.kwargs["completion_tokens"], 3)


if __name__ == "__main__":
    unittest.main()
