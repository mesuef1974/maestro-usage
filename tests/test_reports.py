"""اختبار التقارير 1-3 على قاعدة صناعية بأرقام معروفة."""
import os
import re
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import usage_db
import reports  # noqa: E402


class TestReports(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = usage_db.connect(os.path.join(self.tmp, "u.sqlite3"))
        c = self.con
        c.execute("INSERT INTO sessions(session_key, number, cwd) VALUES ('sA','0101','D:\\x'),('sB',NULL,'D:\\y')")
        def t(i, s, ts, inp, cc, cr, out):
            c.execute("INSERT INTO usage_turns(message_id,session_key,ts,model,input_tokens,cache_creation_tokens,cache_read_tokens,"
                      "output_tokens,thinking_tokens,is_sidechain,source_path) VALUES (?,?,?,?,?,?,?,?,0,0,'p.jsonl')",
                      (i, s, ts, "m", inp, cc, cr, out))
        t("1", "sA", "2026-10-20T01:00:00Z", 1, 0, 400000, 10)   # فوق 300 ألف
        t("2", "sA", "2026-10-21T01:00:00Z", 1, 0, 100000, 10)
        t("3", "sB", "2026-10-22T01:00:00Z", 1, 0, 500000, 100)
        t("4", "sB", "2026-10-23T01:00:00Z", 1, 0, 350000, 100)
        t("5", "sB", "2026-10-28T01:00:00Z", 1, 0, 200000, 50)
        c.commit()

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)



    def test_report3_windows(self):
        self.con.execute("DELETE FROM config_changes")
        self.con.execute("INSERT INTO config_changes(ts,key,old_value,new_value) VALUES ('2026-10-22','K','1','2')")
        self.con.commit()
        r = reports.report3(self.con, today="2026-10-28")[0]
        self.assertEqual(r["before"]["turns"], 2)       # 10-15..10-21: الردّان 1 و2
        self.assertEqual(r["after"]["turns"], 3)        # 10-22..10-28
        self.assertEqual(r["after"]["active_days"], 3)

    def test_report4(self):
        c = self.con
        c.execute("INSERT INTO plan_snapshots(ts, session_key, five_hour_pct, seven_day_pct, source) VALUES "
                  "('2026-10-29T10:00:00.000Z','sA',10,20,'statusline'),('2026-10-29T11:00:00.000Z','sA',30,25,'statusline')")
        c.commit()
        _h, rows4 = reports.report4(c)
        self.assertEqual(rows4[0][:3], ("2026-10-29", "statusline", 2))
        self.assertEqual(rows4[0][3], 25)

    def test_build_writes_files(self):
        path = reports.build(self.con, os.path.join(self.tmp, "out"))
        self.assertTrue(os.path.exists(path))
        html = open(path, encoding="utf-8").read()
        self.assertIn('dir="rtl"', html)
        # بلا موارد خارجية: الرابط الوحيد المسموح هو مساحة أسماء SVG (نص لا طلب)
        self.assertEqual(html.replace("http://www.w3.org/2000/svg", "").count("http"), 0)
        links = re.findall(r"<link[^>]*>", html)  # الرابطان المحلّيان فقط: أيقونة data: والأسلوب المركزي من assets/
        self.assertEqual(len(links), 2, links)
        self.assertTrue(all('href="data:image/svg+xml' in ln or 'href="assets/platform.css?v=' in ln for ln in links), links)
        for bad in ("@import", "XMLHttpRequest", "src=\"http", "<script src"):
            self.assertNotIn(bad, html)
        # الطلب الوحيد المسموح: زر التحديث الفوري نحو الخادم المحلي بمسار نسبي
        # الطلبات الوحيدة مسارات نسبية إلى الخادم المحلي نفسه: التحديث الفوري والقراءة الحيّة للقطات الحصة
        self.assertEqual(html.count("fetch("), html.count('fetch("/refresh"') + html.count('fetch("/plan.json"'))


if __name__ == "__main__":
    unittest.main()
