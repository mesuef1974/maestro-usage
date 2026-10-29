"""اختبار التقارير 1-3 على قاعدة صناعية بأرقام معروفة."""
import os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import usage_db, reports  # noqa: E402


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
        self.con.close(); shutil.rmtree(self.tmp, ignore_errors=True)

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

    def test_build_writes_files(self):
        path = reports.build(self.con, os.path.join(self.tmp, "out"))
        self.assertTrue(os.path.exists(path))
        html = open(path, encoding="utf-8").read()
        self.assertIn('dir="rtl"', html)
        self.assertNotIn("http", html.replace("http-equiv", ""))  # بلا موارد خارجية


if __name__ == "__main__":
    unittest.main()
