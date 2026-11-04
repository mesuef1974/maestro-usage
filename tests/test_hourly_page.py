"""اختبار صفحة «الإجمالي بالساعة»: جدول ساعة × نموذج يطابق قاعدة صناعية بأرقام معروفة."""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import hourly_page  # noqa: E402
import reports  # noqa: E402
import usage_db  # noqa: E402


class TestHourlyPage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = usage_db.connect(os.path.join(self.tmp, "u.sqlite3"))
        c = self.con
        c.execute("INSERT INTO sessions(session_key) VALUES ('aaaaaaaa1'),('bbbbbbbb2')")

        def t(i, s, ts, cc, cr, u=1, model="claude-sonnet-5-5"):
            c.execute("INSERT INTO usage_turns(message_id,session_key,ts,model,input_tokens,cache_creation_tokens,cache_read_tokens,"
                      "output_tokens,thinking_tokens,is_sidechain,source_path,turn_origin) VALUES (?,?,?,?,1,?,?,?,0,0,'p.jsonl','human')",
                      (i, s, ts, model, cc, cr, u))
        t("1", "aaaaaaaa1", "2026-10-20T01:00:00Z", 100, 399_000)
        t("2", "aaaaaaaa1", "2026-10-20T01:10:00Z", 10, 400_000)
        t("3", "aaaaaaaa1", "2026-10-20T03:10:00Z", 5000, 400_000)
        t("6", "bbbbbbbb2", "2026-10-20T01:30:00Z", 0, 10_000, model="model-قديم")
        c.commit()
        self.data = hourly_page.payload(c)

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def hour(self, hh):
        return int(__import__("datetime").datetime.fromisoformat("2026-10-20T%02d:00:00+00:00" % hh).timestamp() // 3600)

    def test_tokens_match_db(self):
        want = self.con.execute(
            "SELECT SUM(input_tokens+cache_creation_tokens+cache_read_tokens+output_tokens) FROM usage_turns").fetchone()[0]
        self.assertEqual(sum(r["k"] for r in self.data["h"]), want)


    def test_old_model_folds_to_other(self):
        other = len(self.data["models"]) - 1
        self.assertTrue(any(r["m"] == other and r["h"] == self.hour(1) for r in self.data["h"]))

    def test_payload_has_numbers_only_and_render_escapes(self):
        for r in self.data["h"]:
            self.assertTrue(all(isinstance(v, int) for v in r.values()))
        self.data["models"][0] = "</script><b>"
        page = hourly_page.render(self.data, "الآن")
        m = re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S)
        self.assertEqual(json.loads(m.group(1))["models"][0], "</script><b>")
        for token in ("__CSS__", "__LIB__", "__DATA__", "__STAMP__"):
            self.assertNotIn(token, page)

    def test_build_writes_hourly_page_without_external_resources(self):
        out = os.path.join(self.tmp, "out")
        reports.build(self.con, out)
        with open(os.path.join(out, "hourly.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertEqual(html.replace("http://www.w3.org/2000/svg", "").count("http"), 0)
        # الطلبات الوحيدة مسارات نسبية إلى الخادم المحلي نفسه: التحديث الفوري والقراءة الحيّة للقطات الحصة
        self.assertEqual(html.count("fetch("), html.count('fetch("/refresh"') + html.count('fetch("/plan.json"'))
        links = re.findall(r"<link[^>]*>", html)  # الرابطان المحلّيان فقط: أيقونة data: والأسلوب المركزي من assets/
        self.assertEqual(len(links), 2, links)
        self.assertTrue(all('href="data:image/svg+xml' in ln or 'href="assets/platform.css?v=' in ln for ln in links), links)
        for bad in ("@import", "XMLHttpRequest", "<script src"):
            self.assertNotIn(bad, html)
        self.assertIn("themebtn", html)  # زر السمة المركزي
        self.assertIn('id="autobtn"', html)  # زر التحديث الدوري تحت زر السمة
        self.assertLess(html.index("mu_theme"), html.index("mu_auto"))
        self.assertLess(html.index("mu_theme"), html.index("</head>"))  # السمة المحفوظة تُطبَّق في الرأس قبل الرسم





    def test_template_texts_follow_actual_window(self):
        page = hourly_page.render(self.data, "الآن")
        self.assertNotIn("wsel", page)  # لا محدّد نافذة عالميًّا: النافذة بحسب الجلسة والنموذج
        self.assertNotIn("250 ألفًا = 100%", page)
        for want in ('id="wdesc"', "النافذة الفعلية لكل جلسة", "w250_spans", "(ناقص)", "الجارية ناقصة", "بعد خمول",
                     "Fable %", "غير مقروءة من /usage منذ", "r.w||WIN", "كل 5 دقائق، وكل دقيقة عند تغيّر النسب"):
            self.assertIn(want, page)
        self.assertNotIn("أُزيلت من الخطة", page)
        self.assertNotIn("خمس ساعات %", page)
        self.assertNotIn("num(p.w,1)", page)  # النسب أعداد صحيحة بلا خانة عشرية


if __name__ == "__main__":
    unittest.main()
