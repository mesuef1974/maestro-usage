"""اختبارات المجمّع والمحمِّل على JSON صناعي بالبنية الموثّقة (مع حقول ناقصة)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import usage_db  # noqa: E402
import statusline_collector as sc  # noqa: E402
import statusline_loader as sl  # noqa: E402

COLLECTOR = os.path.join(os.path.dirname(__file__), "..", "src", "statusline_collector.py")

FULL = {
    "session_id": "abc-123", "transcript_path": "/x/y.jsonl", "model": {"display_name": "نص لا يُحفظ"},
    "cwd": "D:\secret", "cost": {"total_cost_usd": 0.01234},
    "context_window": {"context_window_size": 1000000, "used_percentage": 8,
                       "current_usage": {"input_tokens": 8500, "output_tokens": 1200,
                                         "cache_creation_input_tokens": 5000, "cache_read_input_tokens": 2000}},
    "prompt_cache": {"warm": True, "hit_ratio": 0.91, "requests": 4},
    "rate_limits": {"five_hour": {"used_percentage": 23.5, "resets_at": 1789000000},
                    "seven_day": {"used_percentage": 41.2, "resets_at": 1789500000}},
}


class TestExtract(unittest.TestCase):
    def test_full(self):
        r = sc.extract(FULL)
        self.assertEqual((r["session_key"], r["five_hour_pct"], r["seven_day_pct"]), ("abc-123", 23.5, 41.2))
        self.assertEqual(r["cu_cache_read"], 2000)
        self.assertEqual(r["cache_warm"], 1)
        self.assertTrue(r["seven_day_resets_at"].startswith("2026-"))
        self.assertNotIn("نص", json.dumps(r, ensure_ascii=False))
        self.assertNotIn("secret", json.dumps(r))

    def test_missing_fields(self):
        for d in ({}, {"session_id": "s"}, {"rate_limits": {"five_hour": {"used_percentage": 5}}},
                  {"context_window": {"current_usage": None}}, {"prompt_cache": {"hit_ratio": None}},
                  {"rate_limits": "bad", "cost": 7}):
            r = sc.extract(d)
            self.assertIn("ts", r)

    def test_session_id_must_look_like_id(self):
        self.assertIsNone(sc.extract({"session_id": "نص حر فيه فراغات"})["session_key"])

    def test_status_text(self):
        self.assertEqual(sc.status_text(sc.extract(FULL)), "7d 41% | 5h 24%")
        self.assertEqual(sc.status_text(sc.extract({})), "")


class TestCollectorProcess(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = dict(os.environ)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_collector(self, stdin_bytes, data_dir=None):
        # نسخة معزولة من المجمّع بمجلد data مؤقت كي لا نلوّث data الحقيقي
        src = os.path.join(self.tmp, "src")
        os.makedirs(src, exist_ok=True)
        shutil.copy(COLLECTOR, os.path.join(src, "statusline_collector.py"))
        t = time.time()
        p = subprocess.run([sys.executable, "-I", os.path.join(src, "statusline_collector.py")], input=stdin_bytes,
                           capture_output=True, timeout=20)
        return p, time.time() - t

    def test_never_fails_and_writes_spool(self):
        p, dt = self.run_collector(json.dumps(FULL).encode())
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout.decode(), "7d 41% | 5h 24%")
        spool = os.path.join(self.tmp, "data", "statusline_spool.jsonl")
        self.assertEqual(len(open(spool, encoding="utf-8").read().splitlines()), 1)
        self.assertLess(dt, 2.0)

    def test_garbage_input_is_swallowed_and_logged(self):
        for raw in (b"", b"not json", b"[1,2]", b"\xff\xfe\x00", b"{"):
            p, _ = self.run_collector(raw)
            self.assertEqual(p.returncode, 0)
            self.assertEqual(p.stdout, b"")
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "data", "statusline_errors.log")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "data", "statusline_spool.jsonl")))

    def test_spool_dir_unwritable_does_not_fail(self):
        os.makedirs(os.path.join(self.tmp, "data", "statusline_spool.jsonl"))  # مجلد بدل ملف: الكتابة تفشل
        p, _ = self.run_collector(json.dumps(FULL).encode())
        self.assertEqual(p.returncode, 0)


class TestLoader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.spool = os.path.join(self.tmp, "spool.jsonl")
        self.con = usage_db.connect(os.path.join(self.tmp, "u.sqlite3"))

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add(self, d, ts_ms):
        r = sc.extract(d)
        r["ts"] = "2026-10-29T12:00:%02d.%03dZ" % (ts_ms // 1000, ts_ms % 1000)
        sc.append_spool(r, self.spool)

    def test_load_idempotent_and_incremental(self):
        self.add(FULL, 1000)
        self.add({"session_id": "abc-123", "context_window": {"used_percentage": 9}}, 2000)  # بلا rate_limits
        st = sl.load_spool(self.con, self.spool)
        self.assertEqual((st["samples_new"], st["plans_new"]), (2, 1))
        st = sl.load_spool(self.con, self.spool)
        self.assertEqual((st["lines"], st["samples_new"]), (0, 0))
        self.add(FULL, 3000)
        st = sl.load_spool(self.con, self.spool)
        self.assertEqual((st["samples_new"], st["plans_new"]), (1, 1))
        # إعادة من الصفر لا تضاعف الصفوف
        self.con.execute("UPDATE ingest_state SET offset_bytes=0 WHERE source_path='statusline_spool.jsonl'")
        self.con.commit()
        st = sl.load_spool(self.con, self.spool)
        self.assertEqual((st["samples_new"], st["plans_new"]), (0, 0))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM statusline_samples").fetchone()[0], 3)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM plan_snapshots").fetchone()[0], 2)

    def test_partial_and_bad_lines(self):
        self.add(FULL, 1000)
        with open(self.spool, "a", encoding="utf-8") as f:
            f.write("{bad json}\n")
            f.write('{"ts":"2026-10-29T12:00:09.000Z","sess')  # ناقص بلا سطر جديد
        st = sl.load_spool(self.con, self.spool)
        self.assertEqual((st["samples_new"], st["bad"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
