"""اختبار محلّل ناتج `claude -p "/usage"` ومسجّل اللقطة على نص مأخوذ من ناتج حقيقي."""
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import usage_cli  # noqa: E402
import usage_db  # noqa: E402

SAMPLE = """You are currently using your subscription to power your Claude Code usage

Current session: 4% used · resets Oct 29, 10:50pm (Asia/Qatar)
Current week (all models): 7% used · resets Nov 4, 8pm (Asia/Qatar)
Current week (Fable): 0% used · resets Nov 4, 7:59pm (Asia/Qatar)

What's contributing to your usage?
Approximate · sessions on this machine only · shares overlap

Last 24h · 4069 requests · 85 sessions
  92%  Stop sessions you no longer need · some ran 8 hours or more
  Top MCP servers: ccd_session_mgmt 6%

Last 7d · 27152 requests · 664 sessions
  57%  Stop sessions you no longer need
"""
NOW = datetime(2026, 10, 29, 16, 20, tzinfo=timezone.utc)


class TestUsageCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = usage_db.connect(os.path.join(self.tmp, "u.sqlite3"))
        self.old_log = usage_cli.LOG
        usage_cli.LOG = os.path.join(self.tmp, "usage_cli.log")

    def tearDown(self):
        usage_cli.LOG = self.old_log
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_parse_percentages_resets_and_counts(self):
        p = usage_cli.parse(SAMPLE, NOW)
        self.assertEqual((p["five"], p["seven"], p["fable"]), (4.0, 7.0, 0.0))
        self.assertEqual(p["five_resets"], "2026-10-29T19:50:00Z")      # 22:50 بتوقيت قطر
        self.assertEqual(p["seven_resets"], "2026-11-04T17:00:00Z")     # «8pm» بلا دقائق
        self.assertEqual(p["fable_resets"], "2026-11-04T16:59:00Z")
        self.assertEqual(p["counts"], [("24h", 4069, 85), ("7d", 27152, 664)])

    def test_reset_in_next_year_and_noon_midnight(self):
        late = datetime(2026, 12, 31, 20, 0, tzinfo=timezone.utc)
        p = usage_cli.parse("Current session: 1% used · resets Jan 1, 12am (Asia/Qatar)\n", late)
        self.assertEqual(p["five_resets"], "2026-12-31T21:00:00Z")      # 00:00 قطر = 21:00Z، والشهر 1 ← السنة التالية 2027 بالتوقيت المحلي
        noon = usage_cli.parse("Current session: 1% used · resets Oct 30, 12pm (Asia/Qatar)\n", NOW)
        self.assertEqual(noon["five_resets"], "2026-10-30T09:00:00Z")

    def test_no_windows_returns_none_and_stale_is_detected(self):
        self.assertIsNone(usage_cli.parse("something else entirely", NOW))
        self.assertTrue(usage_cli.is_stale("Showing last-known usage · 12m ago"))
        self.assertTrue(usage_cli.is_stale("rate limited until 3:14am"))
        self.assertFalse(usage_cli.is_stale(SAMPLE))

    def test_record_writes_snapshot_and_counts_once(self):
        p = usage_cli.parse(SAMPLE, NOW)
        self.assertEqual(usage_cli.record(self.con, p, "2026-10-29T16:20:00Z"), 1)
        row = self.con.execute("SELECT five_hour_pct, seven_day_pct, fable_pct, source, plan FROM plan_snapshots").fetchone()
        self.assertEqual(tuple(row), (4.0, 7.0, 0.0, "cli_usage", None))
        self.assertEqual(self.con.execute("SELECT window, requests, sessions FROM cli_usage_counts ORDER BY window").fetchall()[0][1:], (4069, 85))
        usage_cli.record(self.con, p, "2026-10-29T16:20:00Z")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM cli_usage_counts").fetchone()[0], 2)

    def test_main_from_text_file_and_exit_codes(self):
        f = os.path.join(self.tmp, "u.txt")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(SAMPLE)
        db = os.path.join(self.tmp, "u.sqlite3")
        self.assertEqual(usage_cli.main(["--db", db, "--text-file", f]), 0)
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("Showing last-known usage")
        self.assertEqual(usage_cli.main(["--db", db, "--text-file", f]), 2)
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("garbage")
        self.assertEqual(usage_cli.main(["--db", db, "--text-file", f]), 1)
        with open(usage_cli.LOG, encoding="utf-8") as fh:
            self.assertEqual(fh.read().count("\n"), 3)


if __name__ == "__main__":
    unittest.main()
