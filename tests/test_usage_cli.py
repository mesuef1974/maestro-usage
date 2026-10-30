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
        self.assertEqual(usage_cli.record(self.con, p, "2026-10-29T16:20:00Z"), 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM cli_usage_counts").fetchone()[0], 2)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM plan_snapshots").fetchone()[0], 1)

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


class TestDue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "u.sqlite3")
        self.con = usage_db.connect(self.db)
        self.old_log = usage_cli.LOG
        usage_cli.LOG = os.path.join(self.tmp, "usage_cli.log")

    def tearDown(self):
        usage_cli.LOG = self.old_log
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def snap(self, ts, five, seven=7.0, fable=0.0, resets=None):
        self.con.execute("INSERT INTO plan_snapshots(ts, session_key, five_hour_pct, five_hour_resets_at, seven_day_pct, "
                         "source, fable_pct) VALUES (?,NULL,?,?,?,'cli_usage',?)", (ts, five, resets, seven, fable))
        self.con.commit()

    def at(self, hhmmss):
        h, m, s = (int(x) for x in hhmmss.split(":"))
        return datetime(2026, 10, 30, h, m, s, tzinfo=timezone.utc)

    def test_first_snapshot_is_always_due(self):
        self.assertEqual(usage_cli.due(self.con, self.at("10:00:00")), (True, "first"))

    def test_base_interval_five_minutes_with_slack(self):
        self.snap("2026-10-30T10:00:00Z", 1.0)
        self.snap("2026-10-30T10:05:00Z", 1.0)
        self.assertEqual(usage_cli.due(self.con, self.at("10:07:00")), (False, "base"))
        self.assertEqual(usage_cli.due(self.con, self.at("10:09:31")), (True, "base"))

    def test_hot_interval_one_minute_while_percentages_move(self):
        self.snap("2026-10-30T10:00:00Z", 1.0)
        self.snap("2026-10-30T10:05:00Z", 2.0)
        self.assertEqual(usage_cli.due(self.con, self.at("10:05:20")), (False, "hot"))
        self.assertEqual(usage_cli.due(self.con, self.at("10:06:00")), (True, "hot"))
        self.snap("2026-10-30T10:06:00Z", 2.0)       # لا تغيّر ← يعود إلى الفاصل العادي
        self.assertEqual(usage_cli.due(self.con, self.at("10:07:30")), (False, "base"))

    def test_weekly_or_fable_change_also_counts_as_movement(self):
        self.snap("2026-10-30T10:00:00Z", 1.0, seven=7.0)
        self.snap("2026-10-30T10:05:00Z", 1.0, seven=8.0)
        self.assertEqual(usage_cli.due(self.con, self.at("10:06:00")), (True, "hot"))

    def test_window_reset_triggers_immediate_snapshot_once(self):
        self.snap("2026-10-30T10:00:00Z", 4.0, resets="2026-10-30T10:03:00Z")
        self.assertEqual(usage_cli.due(self.con, self.at("10:03:10")), (False, "base"))   # قبل مهلة 20 ثانية
        self.assertEqual(usage_cli.due(self.con, self.at("10:03:25")), (True, "window_reset"))
        self.snap("2026-10-30T10:03:30Z", 0.0)       # لقطة بعد التصفير بلا resets_at جديد ← لا تكرار
        self.assertEqual(usage_cli.due(self.con, self.at("10:03:50")), (False, "hot"))

    def test_after_sleep_snapshot_is_due_immediately(self):
        self.snap("2026-10-30T00:00:00Z", 0.0)
        self.assertEqual(usage_cli.due(self.con, self.at("03:16:30")), (True, "base"))

    def test_main_skips_without_running_claude_unless_forced(self):
        self.snap(usage_db.now_iso(), 1.0)

        def boom():
            raise AssertionError("لا يجوز تشغيل claude عند عدم حلول الموعد")
        real = usage_cli.run_claude
        usage_cli.run_claude = boom
        try:
            self.assertEqual(usage_cli.main(["--db", self.db]), 0)
            self.assertFalse(os.path.exists(usage_cli.LOG))
            usage_cli.run_claude = lambda: SAMPLE
            self.assertEqual(usage_cli.main(["--db", self.db, "--force"]), 0)
        finally:
            usage_cli.run_claude = real
        with open(usage_cli.LOG, encoding="utf-8") as fh:
            self.assertIn("why=forced", fh.read())


if __name__ == "__main__":
    unittest.main()
