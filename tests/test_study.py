"""اختبار جدول الدراسة اليومي على قاعدة صناعية بأرقام معروفة."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import study  # noqa: E402
import usage_db  # noqa: E402


class TestStudy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = usage_db.connect(os.path.join(self.tmp, "u.sqlite3"))
        c = self.con
        c.execute("INSERT INTO sessions(session_key, number, cwd) VALUES ('aaaaaaaa1','0101','D:/x'),('bbbbbbbb2',NULL,'D:/y')")

        def t(i, s, ts, cc, cr, u=1, side=0, org="human"):
            c.execute("INSERT INTO usage_turns(message_id,session_key,ts,model,input_tokens,cache_creation_tokens,cache_read_tokens,"
                      "output_tokens,thinking_tokens,is_sidechain,source_path,turn_origin) VALUES (?,?,?,?,1,?,?,?,0,?,'p.jsonl',?)",
                      (i, s, ts, "claude-sonnet-5-5", cc, cr, u, side, None if side else org))
        t("1", "aaaaaaaa1", "2026-10-20T01:00:00Z", 0, 290_000)
        t("2", "aaaaaaaa1", "2026-10-20T01:05:00Z", 0, 293_000, org="peer")
        t("3", "aaaaaaaa1", "2026-10-20T01:06:00Z", 0, 40_000)              # هبوط من 293001 (مستوى الضغط)
        t("4", "aaaaaaaa1", "2026-10-20T04:00:00Z", 7000, 40_000)           # إيقاظ بعد ساعتين ونصف
        t("5", "aaaaaaaa1", "2026-10-20T04:01:00Z", 0, 5_000, side=1)       # وكيل فرعي لا يدخل الخيط الرئيس
        t("6", "bbbbbbbb2", "2026-10-21T01:00:00Z", 0, 10_000)
        c.commit()
        self.rows = {r["day"]: r for r in study.daily(c)}

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_day_totals_and_per_reply(self):
        r = self.rows["2026-10-20"]
        self.assertEqual((r["replies"], r["main"], r["cr"], r["cc"]), (5, 4, 290_000 + 293_000 + 40_000 + 40_000 + 5_000, 7000))
        self.assertEqual(r["cr_per_reply"], round(r["cr"] / 5))
        self.assertEqual((r["sessions"], r["roles"], r["human"]), (1, 1, 3))
        self.assertEqual(r["peer_pct"], 25.0)

    def test_wake_drop_and_level(self):
        r = self.rows["2026-10-20"]
        self.assertEqual((r["wake"], r["wake_cc"]), (1, 7000))
        self.assertEqual((r["drops"], r["level_med"]), (1, 293_001))
        self.assertEqual(r["max_ctx"], 293_001)

    def test_unnumbered_session_not_a_project_role(self):
        r = self.rows["2026-10-21"]
        self.assertEqual((r["sessions"], r["roles"]), (1, 0))

    def test_first_filter(self):
        self.assertEqual([r["day"] for r in study.daily(self.con, "2026-10-21")], ["2026-10-21"])


if __name__ == "__main__":
    unittest.main()
