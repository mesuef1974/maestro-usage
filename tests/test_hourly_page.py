"""اختبار صفحة «الجلسات بالساعة»: جدول دور × ساعة × نموذج يطابق قاعدة صناعية بأرقام معروفة."""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import hourly_page  # noqa: E402
import regime  # noqa: E402
import role_groups  # noqa: E402
import reports  # noqa: E402
import usage_db  # noqa: E402


class TestHourlyPage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = usage_db.connect(os.path.join(self.tmp, "u.sqlite3"))
        c = self.con
        c.execute("INSERT INTO sessions(session_key, number, cwd) VALUES "
                  "('aaaaaaaa1','0101','D:/x'),('bbbbbbbb2','0101','D:/y'),('cccccccc3',NULL,'D:/z'),('dddddddd4','8094','D:/w'),"
                  "('eeeeeeee5','0202','D:/e'),('ffffffff6','0303','D:/f'),('gggggggg7','0404','D:/g'),('hhhhhhhh8','0505','D:/h')")
        # بدء عمليات معروف: 0404 بعد آخر تغيير (مليون)، و0505 في عهد 250 ألفًا ثم استُؤنفت بعده (النظام من البدء لا من الردّ)
        c.execute("INSERT INTO agent_starts(session_id, started_at, number, kind, pid, first_seen, last_seen) VALUES "
                  "('gggggggg7','2026-10-30T12:00:00Z','0404','cli',1,'2026-10-30T12:00:00Z','2026-10-30T12:00:00Z'),"
                  "('hhhhhhhh8','2026-10-29T12:00:00Z','0505','cli',2,'2026-10-29T12:00:00Z','2026-10-29T12:00:00Z')")

        def t(i, s, ts, cc, cr, u=1, side=0, model="claude-sonnet-5-5"):
            c.execute("INSERT INTO usage_turns(message_id,session_key,ts,model,input_tokens,cache_creation_tokens,cache_read_tokens,"
                      "output_tokens,thinking_tokens,is_sidechain,source_path,turn_origin) VALUES (?,?,?,?,1,?,?,?,0,?,'p.jsonl','human')",
                      (i, s, ts, model, cc, cr, u, side))
        # الساعة 01 (UTC): ردّان؛ الساعة 03: ردّ ثم هبوط من 400 ألف إلى 50 ألفًا ثم وكيل فرعي لا يدخل الضغط
        t("1", "aaaaaaaa1", "2026-10-20T01:00:00Z", 100, 399_000)
        t("2", "aaaaaaaa1", "2026-10-20T01:10:00Z", 10, 400_000)
        t("3", "aaaaaaaa1", "2026-10-20T03:10:00Z", 5000, 400_000)
        t("4", "aaaaaaaa1", "2026-10-20T03:11:00Z", 20, 50_000)
        t("5", "aaaaaaaa1", "2026-10-20T03:12:00Z", 0, 900_000, side=1)
        t("6", "bbbbbbbb2", "2026-10-20T01:30:00Z", 0, 10_000, model="model-قديم")  # دور واحد لجلستين
        t("7", "cccccccc3", "2026-10-20T01:00:00Z", 0, 20_000)  # بلا رقم: فئة «أخرى»
        t("8", "dddddddd4", "2026-10-20T01:00:00Z", 0, 5_000)   # 8094: خارج المشروع
        t("9", "eeeeeeee5", "2026-10-29T10:00:00Z", 0, 100_000)  # جلسة وُلدت في عهد 250 ألفًا وردّها قبل انتهائه: نافذتها 250 ألفًا
        t("10", "ffffffff6", "2026-10-21T05:00:00Z", 0, 300_000)
        t("11", "ffffffff6", "2026-10-21T07:30:00Z", 0, 20_000)  # هبوط بعد فجوة ساعتين ونصف: هبوط بعد خمول
        t("12", "gggggggg7", "2026-10-30T13:00:00Z", 0, 100_000)  # بدء معروف بعد آخر تغيير: مليون
        t("13", "hhhhhhhh8", "2026-10-31T00:00:00Z", 0, 100_000)  # بدء معروف في عهد 250 ألفًا: 250 ألفًا ولو جاء الردّ بعده
        c.commit()
        self.data = hourly_page.payload(c)

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def hour(self, hh):
        return int(__import__("datetime").datetime.fromisoformat("2026-10-20T%02d:00:00+00:00" % hh).timestamp() // 3600)

    def test_project_flag_and_unnumbered_categories(self):
        self.assertEqual(dict(zip(self.data["roles"], self.data["rp"])), {"0101": 1, "0202": 1, "0303": 1, "0404": 1, "0505": 1, "8094": 0, role_groups.OTHER: 0})

    def test_tokens_match_db(self):
        want = self.con.execute(
            "SELECT SUM(input_tokens+cache_creation_tokens+cache_read_tokens+output_tokens) FROM usage_turns").fetchone()[0]
        self.assertEqual(sum(r["k"] for r in self.data["h"]), want)

    def test_hour_buckets_pressure_and_drops(self):
        other = len(self.data["models"]) - 1
        r0 = self.data["roles"].index("0101")
        h1 = [r for r in self.data["h"] if r["r"] == r0 and r["h"] == self.hour(1) and r["m"] != other]
        self.assertEqual(len(h1), 1)
        self.assertEqual(h1[0]["x"], 400_011)  # أكبر سياق في الساعة (1 + 10 + 400000)
        h3 = [r for r in self.data["h"] if r["r"] == r0 and r["h"] == self.hour(3)]
        self.assertEqual(sum(r["d"] for r in h3), 1)
        self.assertEqual((h3[0]["df"], h3[0]["dt"]), (405_001, 50_021))
        self.assertEqual(h3[0]["x"], 405_001)  # الوكيل الفرعي (900 ألف) لا يرفع الضغط
        self.assertEqual(h3[0]["k"], (405_001 + 1) + (50_021 + 1) + (900_001 + 1))

    def test_old_model_folds_to_other(self):
        other = len(self.data["models"]) - 1
        self.assertTrue(any(r["m"] == other and r["h"] == self.hour(1) for r in self.data["h"]))

    def test_payload_has_numbers_only_and_render_escapes(self):
        for r in self.data["h"]:
            self.assertTrue(all(isinstance(v, int) for v in r.values()))
        self.data["roles"][0] = "</script><b>"
        page = hourly_page.render(self.data, "الآن")
        m = re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S)
        self.assertEqual(json.loads(m.group(1))["roles"][0], "</script><b>")
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

    def row(self, role, hh, day="2026-10-20"):
        ri = self.data["roles"].index(role)
        h = int(__import__("datetime").datetime.fromisoformat("%sT%02d:00:00+00:00" % (day, hh)).timestamp() // 3600)
        rows = [r for r in self.data["h"] if r["r"] == ri and r["h"] == h]
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def test_window_per_session_regime_and_model(self):
        other = len(self.data["models"]) - 1
        self.assertEqual(self.data["window"], hourly_page.WINDOW)  # القيمة الاحتياطية تبقى مليونًا
        self.assertEqual(self.row("0101", 3)["w"], 1_000_000)  # قبل أي تغيير: افتراضي = مليون
        self.assertEqual(self.row("0202", 10, "2026-10-29")["w"], 250_000)  # وُلدت في عهد 250 ألفًا
        self.assertEqual(self.row("0404", 13, "2026-10-30")["w"], 1_000_000)  # بدء معروف بعد آخر تغيير
        self.assertEqual(self.row("0505", 0, "2026-10-31")["w"], 250_000)  # بدء معروف في عهد 250 ألفًا
        old = [r for r in self.data["h"] if r["m"] == other]
        self.assertEqual([r["w"] for r in old], [200_000])  # النموذج الأقدم: نافذته 200 ألف أيًّا كان النظام
        self.assertEqual(hourly_page.window_of(regime.W250, other), 200_000)
        self.assertEqual(hourly_page.window_of(regime.UNKNOWN, 0), 1_000_000)
        # ساعة بلا ردّ رئيس (الوكيل الفرعي وحده) لا نافذة لها: w = 0 فتقع الصفحة على الاحتياطي
        self.assertTrue(all(r["w"] > 0 or r["x"] == 0 for r in self.data["h"]))

    def test_windows_meta_from_config_changes(self):
        W = self.data["windows"]
        ch = regime.changes()
        want = [[ts, ch[i + 1][0] if i + 1 < len(ch) else None] for i, (ts, code) in enumerate(ch) if code == regime.W250]
        self.assertEqual(W["w250_spans"], want)
        self.assertTrue(want and "T" in want[0][0] and want[0][1])  # فترة واحدة مغلقة لنظام 250 ألفًا في البذور
        notes = " ".join(n or "" for *_r, n in usage_db.CONFIG_SEEDS)
        pcts = sorted({int(m) for m in re.findall(r"autoCompactsAtPercent=(\d+)", notes)})
        self.assertEqual(W["autocompact_pct"], [pcts[0], pcts[-1]])
        self.assertEqual((W["default"], W["w250"], W["old"]), (1_000_000, 250_000, 200_000))
        self.assertEqual(self.data["wake_gap"], 3600)

    def test_drop_after_idle_counter(self):
        r = self.row("0303", 7, "2026-10-21")
        self.assertEqual((r["d"], r["di"], r["df"], r["dt"]), (1, 1, 300_001, 20_001))
        r3 = self.row("0101", 3)
        self.assertEqual((r3["d"], r3["di"]), (1, 0))  # هبوط بعد دقيقة واحدة: ليس بعد خمول

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
