"""كلفة الحصة على قاعدة صناعية: الانتقالات الدقيقة فقط تدخل التقدير، والفجوات الطويلة تُسقط، والتوقّع يُحسب من آخر 24 ساعة."""
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import quota_model  # noqa: E402
import usage_db  # noqa: E402

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


class TestQuotaModel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = usage_db.connect(os.path.join(self.tmp, "t.sqlite3"))
        self.con.execute("INSERT INTO sessions(session_key, number, cwd) VALUES ('s','0440','D:/x')")
        self.n = 0

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def snap(self, ts, pct, fa=None):
        self.con.execute("INSERT INTO plan_snapshots(ts, seven_day_pct, seven_day_resets_at, fable_pct, fable_resets_at, source) "
                         "VALUES (?,?,'2026-11-04T17:00:00Z',?,'2026-11-04T17:00:00Z','cli_usage')", (ts, pct, fa))

    def turn(self, ts, tokens, model="claude-sonnet-5-5"):
        self.n += 1
        self.con.execute("INSERT INTO usage_turns(message_id,session_key,ts,model,input_tokens,cache_creation_tokens,cache_read_tokens,"
                         "output_tokens,thinking_tokens,is_sidechain,source_path) VALUES (?,?,?,?,0,0,?,0,0,0,'p.jsonl')",
                         (str(self.n), "s", ts, model, tokens))

    def test_precise_pairs_only(self):
        # لقطات كل 5 دقائق: 4 → 5 عند 10:05، 5 → 6 عند 10:25، 6 → 7 عند 10:45، ثم فجوة ساعتين ثم 7 → 8 (غير دقيق)
        for m in range(0, 50, 5):
            self.snap("2026-10-30T10:%02d:00Z" % m, 4 if m < 5 else 5 if m < 25 else 6 if m < 45 else 7)
        self.snap("2026-10-30T12:50:00Z", 8)
        self.turn("2026-10-30T10:10:00Z", 100)
        self.turn("2026-10-30T10:30:00Z", 300)
        self.turn("2026-10-30T11:30:00Z", 10_000)  # داخل الفجوة: يجب ألا يدخل
        self.con.commit()
        tr = quota_model.transitions(self.con, "seven_day_pct")
        self.assertEqual([(t[3], t[4]) for t in tr], [(5, True), (6, True), (7, True), (8, False)])
        ps = quota_model.pairs(self.con, "seven_day_pct")
        self.assertEqual([(d, t) for _a, _b, d, t in ps], [(1, 100), (1, 300)])
        self.assertEqual(quota_model.cost(self.con, "seven_day_pct")["per_pct"], None)  # زوجان < MIN_PAIRS

    def test_cost_and_forecast(self):
        pct = 4
        for k in range(0, 8):  # صعود كل 10 دقائق مع لقطة كل 5
            base = 10 * k
            self.snap("2026-10-31T%02d:%02d:00Z" % (8 + base // 60, base % 60), pct)
            self.snap("2026-10-31T%02d:%02d:00Z" % (8 + (base + 5) // 60, (base + 5) % 60), pct)
            pct += 1
            self.turn("2026-10-31T%02d:%02d:30Z" % (8 + (base + 5) // 60, (base + 5) % 60), 80)
        self.con.commit()
        c = quota_model.cost(self.con, "seven_day_pct")
        self.assertEqual(c["n"], 6)
        self.assertAlmostEqual(c["per_pct"], 80)
        self.assertEqual((c["lo"], c["hi"]), (80, 80))
        fc = quota_model.forecast(self.con, "seven_day_pct", "seven_day_resets_at", c["per_pct"], now=NOW)
        self.assertEqual(fc["pct"], 11)
        self.assertEqual(fc["rate_src"], "tokens")  # لا لقطة قبل 24 ساعة فالاحتياط التوكنات
        self.assertAlmostEqual(fc["rate_day"], 8 * 80 / 80)  # 640 توكن في آخر 24 ساعة ÷ 80 = 8% يوميًّا
        hours_left = (datetime(2026, 11, 4, 17, tzinfo=timezone.utc) - NOW).total_seconds() / 3600
        self.assertAlmostEqual(fc["at_reset"], 11 + 8 / 24 * hours_left)
        self.assertIsNone(fc["full_at"])

    def test_observed_rate_and_plan_boundary(self):
        # لقطات بنافذة الخمس ساعات (الخطة القديمة) ثم اختفاؤها: الأزواج قبل الحدّ تُسقط، والحرق يُرصد من اللقطتين لا من التوكنات
        for h, p in ((0, 2), (1, 3), (2, 4)):
            self.con.execute("INSERT INTO plan_snapshots(ts, five_hour_pct, seven_day_pct, seven_day_resets_at, source) VALUES (?,10,?,'2026-11-04T17:00:00Z','cli_usage')",
                             ("2026-10-30T%02d:00:00Z" % (8 + h), p))
            self.con.execute("INSERT INTO plan_snapshots(ts, five_hour_pct, seven_day_pct, seven_day_resets_at, source) VALUES (?,10,?,'2026-11-04T17:00:00Z','cli_usage')",
                             ("2026-10-30T%02d:05:00Z" % (8 + h), p))
            self.turn("2026-10-30T%02d:02:00Z" % (8 + h), 1000)
        self.snap("2026-10-30T11:00:00Z", 5)
        self.snap("2026-10-30T11:05:00Z", 5)
        self.snap("2026-10-31T11:00:00Z", 11)  # بعد نحو 24 ساعة: +6%
        self.con.commit()
        self.assertEqual(quota_model.plan_since(self.con), "2026-10-30T10:05:00Z")
        self.assertEqual(quota_model.pairs(self.con, "seven_day_pct"), [])  # كل الأزواج تبدأ قبل الحدّ
        fc = quota_model.forecast(self.con, "seven_day_pct", "seven_day_resets_at", None, now=NOW)
        self.assertEqual((fc["rate_src"], fc["obs_from"]), ("observed", "2026-10-30T11:05:00Z"))
        self.assertAlmostEqual(fc["rate_day"], 6 / (24 - 5 / 60) * 24)
        self.assertIsNotNone(fc["at_reset"])

    def test_full_before_reset(self):
        self.snap("2026-10-31T11:00:00Z", 90)
        self.turn("2026-10-31T11:30:00Z", 2400)
        self.con.commit()
        fc = quota_model.forecast(self.con, "seven_day_pct", "seven_day_resets_at", 1.0, now=NOW)
        self.assertEqual(fc["rate_day"], 2400)  # 100%/ساعة
        self.assertEqual(fc["full_at"], "2026-10-31T12:06:00Z")

    def test_payload_shape_and_fable_filter(self):
        self.snap("2026-10-31T11:00:00Z", 10, fa=2)
        self.turn("2026-10-31T11:30:00Z", 500, model="claude-fable-5-1")
        self.con.commit()
        p = quota_model.payload(self.con, now=NOW)
        self.assertEqual(set(p), {"week", "fable"})
        self.assertEqual(p["fable"]["cost"], dict(since=None, n=0, per_pct=None))
        self.assertEqual(p["fable"]["fc"]["pct"], 2)
        self.assertEqual(quota_model._tokens(self.con, "2026-10-31T00:00:00Z", "2026-11-01T00:00:00Z", "claude-fable-%"), 500)
        self.assertEqual(quota_model._tokens(self.con, "2026-10-31T00:00:00Z", "2026-11-01T00:00:00Z", "claude-opus-%"), 0)


if __name__ == "__main__":
    unittest.main()
