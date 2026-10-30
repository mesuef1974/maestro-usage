"""اختبار حمولة اللوحة التفاعلية: الأرقام تطابق القاعدة، ولا نص حرّ خارج الأسماء المعروفة."""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import dashboard  # noqa: E402
import reports  # noqa: E402
import usage_db  # noqa: E402


class TestDashboard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = usage_db.connect(os.path.join(self.tmp, "u.sqlite3"))
        c = self.con
        c.execute("INSERT INTO sessions(session_key, number, cwd) VALUES ('sA','0101','D:/x'),('sB',NULL,'D:/y')")

        def t(i, s, ts, model, inp, cc, cr, out, org=None):
            c.execute("INSERT INTO usage_turns(message_id,session_key,ts,model,input_tokens,cache_creation_tokens,cache_read_tokens,"
                      "output_tokens,thinking_tokens,is_sidechain,source_path,turn_origin) VALUES (?,?,?,?,?,?,?,?,0,0,'p.jsonl',?)",
                      (i, s, ts, model, inp, cc, cr, out, org))
        t("1", "sA", "2026-10-20T01:00:00Z", "claude-sonnet-5-5", 1, 0, 400000, 10, "human")  # فوق العتبة
        t("2", "sA", "2026-10-20T02:00:00Z", "claude-opus-4-8", 1, 5, 100000, 10, "scheduled")  # نموذج قديم → أخرى
        t("3", "sB", "2026-10-22T01:00:00Z", "claude-sonnet-5-5", 1, 0, 500000, 100, None)
        t("4", "sB", "2026-10-22T05:00:00Z", "model-غير-معروف", 1, 0, 200000, 50, "weird")
        c.execute("INSERT INTO plan_snapshots(ts, five_hour_pct, seven_day_pct, source) VALUES ('2026-10-22T06:00:00Z',3,5,'get_usage')")
        c.commit()
        self.data = dashboard.payload(c, reports.session_label, reports.NOT_APPLIED_MARK, 50)

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_totals_match_db(self):
        want = self.con.execute("SELECT COUNT(*), SUM(cache_read_tokens), SUM(output_tokens) FROM usage_turns").fetchone()
        a, b = self.data["a"], self.data["b"]
        for rows in (a, b):
            self.assertEqual((sum(r["t"] for r in rows), sum(r["cr"] for r in rows), sum(r["u"] for r in rows)), tuple(want))
        self.assertEqual(sum(r["v"] for r in a), 2)  # الردّان فوق 300 ألف
        self.assertEqual(max(r["mx"] for r in b), 500001)

    def test_model_and_origin_folding(self):
        other = len(dashboard.MODEL_GROUPS)
        self.assertEqual({r["m"] for r in self.data["a"]}, {0, other})  # القديم وغير المعروف في «أخرى»
        self.assertEqual({r["g"] for r in self.data["a"]}, {"human", "scheduled", "unknown"})  # NULL وweird → unknown
        self.assertEqual(len(self.data["models"]), other + 1)

    def test_plan_and_changes(self):
        self.assertEqual(self.data["plan"], [dict(ts="2026-10-22T06:00:00Z", f=3.0, fr=None, w=5.0, src="get_usage")])
        applied = {(c["key"], c["new"]): c["applied"] for c in self.data["changes"]}
        self.assertFalse(applied[("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "25")])
        self.assertTrue(applied[("autoCompactWindow", "250000")])

    def test_render_embeds_valid_json_and_escapes(self):
        self.data["sessions"][0]["label"] = "</script><b>"
        page = dashboard.render(self.data, "<p>ساكن</p>", "الآن")
        m = re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S)
        got = json.loads(m.group(1))
        self.assertEqual(got["sessions"][0]["label"], "</script><b>")
        self.assertNotIn("__DATA__", page)
        self.assertNotIn("__STATIC__", page)
        self.assertIn("ساكن", page)

    def test_payload_has_only_numbers_and_known_names(self):
        """الحقول النصية الوحيدة: اليوم/الوقت، أصل الدور المعروف، اسم الجلسة المشتق من الرقم والمعرّف والمجلد، ومفاتيح الإعداد."""
        for r in self.data["a"]:
            self.assertRegex(r["d"], r"^\d{4}-\d\d-\d\d$")
            self.assertIn(r["g"], dashboard.ORIGINS)
        for r in self.data["b"]:
            self.assertIsInstance(r["s"], int)
        for s in self.data["sessions"]:
            self.assertEqual(set(s), {"label"})


if __name__ == "__main__":
    unittest.main()
