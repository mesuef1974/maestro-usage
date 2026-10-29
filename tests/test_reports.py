"""اختبار التقارير 1-3 على قاعدة صناعية بأرقام معروفة."""
import os
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

    def test_report1_order_by_ratio(self):
        reports.MIN_TURNS_SUMMARY = 1
        _h, rows, summ = reports.report1(self.con)
        self.assertEqual(summ[0][0], "sA")  # 500000/20 = 25000 أعلى من 1050000/250
        self.assertAlmostEqual(summ[0][6], 25000.0)
        self.assertEqual(len(rows), 5)  # sA يومان + sB ثلاثة أيام

    def test_report2_counts_over_threshold(self):
        _h, rows, totals = reports.report2(self.con)
        got = {r[0]: r[4] for r in rows}
        self.assertEqual(got, {"sA": 1, "sB": 2})
        self.assertEqual(totals[:2], (5, 3))

    def test_report3_windows(self):
        self.con.execute("DELETE FROM config_changes")
        self.con.execute("INSERT INTO config_changes(ts,key,old_value,new_value) VALUES ('2026-10-22','K','1','2')")
        self.con.commit()
        r = reports.report3(self.con, today="2026-10-28")[0]
        self.assertEqual(r["before"]["turns"], 2)       # 10-15..10-21: الردّان 1 و2
        self.assertEqual(r["after"]["turns"], 3)        # 10-22..10-28
        self.assertEqual(r["after"]["active_days"], 3)

    def test_report4_and_5(self):
        c = self.con
        c.execute("INSERT INTO plan_snapshots(ts, session_key, five_hour_pct, seven_day_pct, source) VALUES "
                  "('2026-10-29T10:00:00.000Z','sA',10,20,'statusline'),('2026-10-29T11:00:00.000Z','sA',30,25,'statusline')")
        c.execute("UPDATE sessions SET number='0101' WHERE session_key='sA'")
        # عشر دورات مجدولة كل 300 ثانية، كل منها ردّان متلاحقان
        for i in range(10):
            for j in range(2):
                mm, ss = divmod(i * 300 + j * 5, 60)
                hh, mm = divmod(mm, 60)
                c.execute("INSERT INTO usage_turns(message_id,session_key,ts,model,input_tokens,cache_creation_tokens,cache_read_tokens,"
                          "output_tokens,thinking_tokens,is_sidechain,source_path,turn_origin) VALUES (?,?,?,?,1,0,1000,5,0,0,'p.jsonl','scheduled')",
                          ("s%d_%d" % (i, j), "sA", "2026-10-25T%02d:%02d:%02dZ" % (hh, mm, ss), "m"))
        c.commit()
        _h, rows4 = reports.report4(c)
        self.assertEqual(rows4[0][:3], ("2026-10-29", "statusline", 2))
        self.assertEqual(rows4[0][3], 25)
        r5 = reports.report5(c)
        self.assertEqual((r5["turns"], r5["runs"], r5["cache_read"]), (20, 10, 20000))
        self.assertEqual(round(r5["gap"]["median"]), 300)
        self.assertEqual(r5["gap"]["near5"], 1.0)

    def test_build_writes_files(self):
        path = reports.build(self.con, os.path.join(self.tmp, "out"))
        self.assertTrue(os.path.exists(path))
        html = open(path, encoding="utf-8").read()
        self.assertIn('dir="rtl"', html)
        # بلا موارد خارجية: الرابط الوحيد المسموح هو مساحة أسماء SVG (نص لا طلب)
        self.assertEqual(html.replace("http://www.w3.org/2000/svg", "").count("http"), 0)
        for bad in ("<link", "@import", "XMLHttpRequest", "src=\"http", "<script src"):
            self.assertNotIn(bad, html)
        # الطلب الوحيد المسموح: زر التحديث الفوري نحو الخادم المحلي بمسار نسبي
        self.assertEqual(html.count("fetch("), html.count('fetch("/refresh"'))


if __name__ == "__main__":
    unittest.main()
