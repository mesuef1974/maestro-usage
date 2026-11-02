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

        def t(i, s, ts, model, inp, cc, cr, out, org=None, side=0):
            c.execute("INSERT INTO usage_turns(message_id,session_key,ts,model,input_tokens,cache_creation_tokens,cache_read_tokens,"
                      "output_tokens,thinking_tokens,is_sidechain,source_path,turn_origin) VALUES (?,?,?,?,?,?,?,?,0,?,'p.jsonl',?)",
                      (i, s, ts, model, inp, cc, cr, out, side, org))
        t("1", "sA", "2026-10-20T01:00:00Z", "claude-sonnet-5-5", 1, 0, 400000, 10, "human")  # فوق العتبة
        t("2", "sA", "2026-10-20T02:00:00Z", "claude-opus-4-8", 1, 5, 100000, 10, "scheduled")  # نموذج قديم → أخرى
        t("3", "sB", "2026-10-22T01:00:00Z", "claude-sonnet-5-5", 1, 0, 500000, 100, None)
        t("4", "sB", "2026-10-22T05:00:00Z", "model-غير-معروف", 1, 0, 200000, 50, "weird")
        # ردّا وكيل فرعي في sB (بلا أصل): أحدهما فوق العتبة وأكبر من كل الرئيسة؛ يدخلان في الاستهلاك لا في الضغط
        t("5", "sB", "2026-10-22T06:00:00Z", "claude-sonnet-5-5", 1, 0, 600000, 20, None, side=1)
        t("6", "sB", "2026-10-22T07:00:00Z", "claude-sonnet-5-5", 1, 0, 1000, 20, None, side=1)
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
        self.assertEqual(sum(r["v"] for r in a), 3)  # الردود الثلاثة فوق 300 ألف (منها واحد لوكيل فرعي)
        self.assertEqual(max(r["mx"] for r in b), 500001)  # أكبر سياق من الخيط الرئيس؛ 600001 للوكيل الفرعي لا يُحتسب

    def test_main_thread_fields(self):
        """الحقول m… للخيط الرئيس فقط: العدد والمجاميع وفوق العتبة في A، والعدد والعتبة ومجموع سياقها في B."""
        a, b = self.data["a"], self.data["b"]
        self.assertEqual((sum(r["mt"] for r in a), sum(r["mv"] for r in a)), (4, 2))
        self.assertEqual(sum(r["mi"] + r["mcc"] + r["mcr"] for r in a), 4 + 5 + 400000 + 100000 + 500000 + 200000)
        sub = [r for r in a if r["g"] == "sub"]
        self.assertEqual((len(sub), sub[0]["t"], sub[0]["mt"], sub[0]["cr"], sub[0]["v"], sub[0]["mv"]), (1, 2, 0, 601000, 1, 0))
        row = next(r for r in b if r["t"] == 3)  # sB × 2026-10-22 × Sonnet 5.5: ردّ رئيس وردّا وكيل
        self.assertEqual((row["mt"], row["v"], row["mv"], row["mx"], row["cv"]), (1, 2, 1, 500001, 500001))

    def test_model_and_origin_folding(self):
        other = len(dashboard.MODEL_GROUPS)
        self.assertEqual({r["m"] for r in self.data["a"]}, {0, other})  # القديم وغير المعروف في «أخرى»
        self.assertEqual({r["g"] for r in self.data["a"]}, {"human", "scheduled", "unknown", "sub"})  # NULL وweird → unknown؛ الوكيل الفرعي → sub
        self.assertEqual(len(self.data["models"]), other + 1)

    def test_plan_and_changes(self):
        self.assertEqual(self.data["plan"], [dict(ts="2026-10-22T06:00:00Z", f=3.0, fr=None, w=5.0, wr=None, fa=None, far=None, pl=None, src="get_usage")])
        applied = {(c["key"], c["new"]): c["applied"] for c in self.data["changes"]}
        self.assertFalse(applied[("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "25")])
        self.assertTrue(applied[("autoCompactWindow", "250000")])

    def test_render_embeds_valid_json_and_escapes(self):
        self.data["sessions"][0]["label"] = "</script><b>"
        page = dashboard.render(self.data, "<p>ساكن</p>", "الآن", "heavy.html")  # صفحة فيها قسم الجلسات فلا تُقلَّم حمولتها
        m = re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S)
        got = json.loads(m.group(1))
        self.assertEqual(got["sessions"][0]["label"], "</script><b>")
        self.assertNotIn("__DATA__", page)
        self.assertNotIn("__STATIC__", page)
        self.assertIn("ساكن", dashboard.render(self.data, "<p>ساكن</p>", "الآن", "data.html"))  # الجزء الساكن في صفحة البيانات فقط

    def test_index_has_month_bars_with_needed_data(self):
        """الصفحة الرئيسية فيها قسم توكنز كل شهر وحمولتها تحمل المصفوفة a التي يجمّع منها JS الأشهر."""
        page = dashboard.render(self.data, "", "الآن", "index.html")
        self.assertIn('id="cm"', page)
        self.assertIn("function renderMonth", page)
        m = re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S)
        self.assertTrue(json.loads(m.group(1))["a"])

    def test_template_uses_main_thread_and_live_forecast(self):
        """القالب يقرأ الحقول الرئيسة في المؤشرات والجلسات والضغط، ويُعيد حساب المتوقَّع من النسبة الحيّة، ويعرض زمن آخر عيّنة بدء."""
        page = dashboard.render(self.data, "", "الآن", "index.html")
        for s in ('sum(rows,"mt")', "(الخيط الرئيس)", "function quotaForecast", 'quotaLine("lr7q",D.quota&&D.quota.week,last.w,last.wr,now)',
                  'id="lalert"', "function quotaAlert", "تحذير: بمعدل الحرق الحالي",
                  "RATE_SRC[f.rate_src]", "o.mt+=r.mt", "c.last_ts", "(جزئي من ", "، ناقص)", "حدّ أدنى 10%"):
            self.assertIn(s, page)
        self.assertNotIn("حدّ أدنى 20%", page)

    def test_plan_payload_carries_fable(self):
        self.con.execute("INSERT INTO plan_snapshots(ts, seven_day_pct, fable_pct, fable_resets_at, source) "
                         "VALUES ('2026-10-23T06:00:00Z',12,2,'2026-11-04T17:00:00Z','cli_usage')")
        self.con.commit()
        data = dashboard.payload(self.con, reports.session_label, reports.NOT_APPLIED_MARK, 50)
        last = data["plan"][-1]
        self.assertEqual((last["fa"], last["far"]), (2.0, "2026-11-04T17:00:00Z"))
        page = dashboard.render(data, "", "الآن", "index.html")
        self.assertIn('id="lrf"', page)

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
