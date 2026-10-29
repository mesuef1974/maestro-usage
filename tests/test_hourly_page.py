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
import role_groups  # noqa: E402
import reports  # noqa: E402
import usage_db  # noqa: E402


class TestHourlyPage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = usage_db.connect(os.path.join(self.tmp, "u.sqlite3"))
        c = self.con
        c.execute("INSERT INTO sessions(session_key, number, cwd) VALUES "
                  "('aaaaaaaa1','0101','D:/x'),('bbbbbbbb2','0101','D:/y'),('cccccccc3',NULL,'D:/z'),('dddddddd4','8094','D:/w')")

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
        c.commit()
        self.data = hourly_page.payload(c)

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def hour(self, hh):
        return int(__import__("datetime").datetime.fromisoformat("2026-10-20T%02d:00:00+00:00" % hh).timestamp() // 3600)

    def test_project_flag_and_unnumbered_categories(self):
        self.assertEqual(dict(zip(self.data["roles"], self.data["rp"])), {"0101": 1, "8094": 0, role_groups.OTHER: 0})

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
        self.assertEqual(html.count("fetch("), html.count('fetch("/refresh"'))
        for bad in ("<link", "@import", "XMLHttpRequest", "<script src"):
            self.assertNotIn(bad, html)
        self.assertIn("themebtn", html)  # زر السمة المركزي
        self.assertLess(html.index("mu_theme"), html.index("</head>"))  # السمة المحفوظة تُطبَّق في الرأس قبل الرسم


if __name__ == "__main__":
    unittest.main()
