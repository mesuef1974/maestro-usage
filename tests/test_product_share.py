import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import product_share  # noqa: E402


class TestProductShare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "product_share.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_then_payload_gives_factor(self):
        now = datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc)
        out = product_share.save({"claude_code": 13, "cowork": 86, "chats": 1}, self.path, now)
        self.assertEqual(out["other"], 0.0)
        self.assertEqual(json.load(open(self.path, encoding="utf-8"))["saved_at"], "2026-11-05T08:00:00Z")
        p = product_share.payload(self.path, now)
        self.assertAlmostEqual(p["factor"], 100 / 13, places=4)
        self.assertEqual(p["age_days"], 0)
        self.assertFalse(p["stale"])
        self.assertTrue(product_share.payload(self.path, datetime(2026, 11, 20, tzinfo=timezone.utc))["stale"])

    def test_rejects_bad_input(self):
        for bad in ({"claude_code": 120, "cowork": 0}, {"claude_code": 10, "cowork": 10}, {"claude_code": "13", "cowork": 87}, []):
            with self.assertRaises(ValueError):
                product_share.validate(bad)

    def test_missing_file_means_no_factor(self):
        p = product_share.payload(os.path.join(self.tmp, "none.json"))
        self.assertIsNone(p["factor"])
        self.assertTrue(p["stale"])


if __name__ == "__main__":
    unittest.main()
