"""اختبار قياس كلفة بدء الجلسة: العيّنات، بصمات المصادر، حكم الأثر، وحدود الجلسات المستأنفة."""
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import startup_cost as sc  # noqa: E402
import usage_db  # noqa: E402

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def iso(i):
    return (T0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ")


class TestStartupCost(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = usage_db.connect(os.path.join(self.tmp, "u.sqlite3"))

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sample(self, i, ctx, folder="F", proj="P"):
        self.con.execute("INSERT INTO startup_samples(session_key, ts, ctx, folder, proj) VALUES (?,?,?,?,?)", ("s%d" % i, iso(i), ctx, folder, proj))

    def test_refresh_takes_first_main_turn_only(self):
        c = self.con
        c.execute("INSERT INTO sessions(session_key, cwd) VALUES ('a','D:/x/proj')")
        for mid, ts, side, inp, cc, cr in (("1", iso(1), 0, 5, 1000, 29000), ("2", iso(0), 1, 9, 9, 9), ("3", iso(2), 0, 1, 1, 90000)):
            c.execute("INSERT INTO usage_turns(message_id,session_key,ts,model,input_tokens,cache_creation_tokens,cache_read_tokens,output_tokens,"
                      "thinking_tokens,is_sidechain,source_path) VALUES (?,?,?,?,?,?,?,1,0,?,?)", (mid, "a", ts, "claude-sonnet-5-5", inp, cc, cr, side, "PRJ/a.jsonl"))
        self.assertEqual(sc.refresh_samples(c), 1)
        self.assertEqual(sc.refresh_samples(c), 0)  # لا تكرار
        r = c.execute("SELECT ctx, proj, folder FROM startup_samples").fetchone()
        self.assertEqual(r[:2], (30005, "PRJ"))

    def test_fingerprints_baseline_then_change(self):
        items = {"settings:startup": ("a" * 64, 10)}
        self.assertEqual(sc.check_fingerprints(self.con, iso(0), items), [])  # خط الأساس ليس تغييرًا
        self.assertEqual(sc.check_fingerprints(self.con, iso(1), items), [])
        self.assertEqual(sc.check_fingerprints(self.con, iso(2), {"settings:startup": ("b" * 64, 7)}), [("settings:startup", 10, 7)])
        ch = sc.changes(self.con)
        self.assertEqual([(c["ts"], c["b0"], c["b1"]) for c in ch], [(iso(2), 10, 7)])

    def test_verdict_pending_lower_inconclusive(self):
        for i in range(30):  # قبل ≈ 50 ألفًا
            self.sample(i, 50_000 + (i % 3) * 100)
        self.con.execute("INSERT INTO config_fingerprints(ts,item,sha,bytes) VALUES (?,?,?,?),(?,?,?,?)",
                         (iso(0), "claudemd:global", "a" * 64, 100, iso(30), "claudemd:global", "b" * 64, 50))
        for i in range(30, 36):
            self.sample(i, 40_000)
        fx = sc.effects(self.con)
        self.assertEqual(fx[0]["verdict"], "pending")  # 6 جلسات فقط بعد التعديل
        for i in range(36, 50):
            self.sample(i, 40_000 + (i % 3) * 100)
        fx = sc.effects(self.con)
        self.assertEqual(fx[0]["verdict"], "lower")
        self.assertLess(fx[0]["delta"], -9_000)
        self.assertEqual((fx[0]["nb"], fx[0]["na"]), (20, 20))

    def test_small_delta_is_inconclusive_and_resumed_excluded(self):
        for i in range(25):
            self.sample(i, 40_000 + (i % 5) * 300)
        self.sample(25, 500_000)  # جلسة مستأنفة: خارج القياس
        self.con.execute("INSERT INTO config_fingerprints(ts,item,sha,bytes) VALUES (?,?,?,?),(?,?,?,?)",
                         (iso(0), "skills:user", "a" * 64, 1, iso(25), "skills:user", "b" * 64, 2))
        for i in range(26, 50):
            self.sample(i, 39_000 + (i % 5) * 300)
        e = sc.effects(self.con)[0]
        self.assertEqual(e["verdict"], "inconclusive")
        self.assertLess(e["ma"], 50_000)

    def test_scope_isolates_folders(self):
        for i in range(40):
            self.sample(i, 50_000, folder="A")
            self.sample(100 + i, 30_000, folder="B")
        self.con.execute("INSERT INTO config_fingerprints(ts,item,sha,bytes) VALUES (?,?,?,?),(?,?,?,?)",
                         (iso(0), "claudemd:folder:A", "a" * 64, 9, iso(20), "claudemd:folder:A", "b" * 64, 3))
        e = sc.effects(self.con)[0]
        self.assertEqual((e["scope"], e["mb"], e["ma"]), ("A", 50_000, 50_000))  # أثر B لا يلوّث A

    def test_payload_shape_empty(self):
        p = sc.payload(self.con)
        self.assertEqual((p["daily"], p["fx"]), ([], []))
        self.assertIsNone(p["cur"]["med"])


if __name__ == "__main__":
    unittest.main()
