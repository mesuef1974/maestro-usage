"""اختبار التقاط تشغيلات الجلسات الحيّة: التحليل، التكرار الآمن، رصد إعادة التشغيل، وربط الرقم احتياطًا."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import agents_cli  # noqa: E402
import usage_db  # noqa: E402

T1 = 1793340808449  # 2026-10-30T06:13:28.449Z


def blob(*rows):
    return json.dumps([dict(sessionId=s, kind="interactive", name=n, pid=p, startedAt=t, status="idle", cwd="D:/x") for s, n, p, t in rows])


class TestAgents(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = usage_db.connect(os.path.join(self.tmp, "u.sqlite3"))

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_parse_keeps_number_not_name(self):
        rows = agents_cli.parse(blob(("s1", "0440 · التحوّل: نص طويل", 11, T1), ("s2", "بلا رقم", 12, T1)))
        self.assertEqual(rows[0], ("s1", "2026-10-30T06:13:28.449Z", "0440", "interactive", 11))
        self.assertIsNone(rows[1][2])

    def test_parse_ignores_garbage(self):
        self.assertEqual(agents_cli.parse("ليس json"), [])
        self.assertEqual(agents_cli.parse('{"a":1}'), [])
        self.assertEqual(agents_cli.parse(json.dumps([{"sessionId": "bad id!", "startedAt": T1}, {"sessionId": "ok", "startedAt": "x"}, 5])), [])

    def test_record_idempotent_and_restart_detected(self):
        rows = agents_cli.parse(blob(("s1", "0101 · أ", 1, T1)))
        self.assertEqual(agents_cli.record(self.con, rows, "2026-10-30T07:00:00Z"), (1, 0))
        self.assertEqual(agents_cli.record(self.con, rows, "2026-10-30T07:05:00Z")[0], 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*), MIN(first_seen), MAX(last_seen) FROM agent_starts").fetchone(),
                         (1, "2026-10-30T07:00:00Z", "2026-10-30T07:05:00Z"))
        again = agents_cli.parse(blob(("s1", "0101 · أ", 2, T1 + 3_600_000)))  # عملية جديدة لنفس الجلسة
        self.assertEqual(agents_cli.record(self.con, again, "2026-10-30T08:00:00Z")[0], 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM agent_starts WHERE session_id='s1'").fetchone()[0], 2)

    def test_number_fills_only_missing(self):
        self.con.execute("INSERT INTO sessions(session_key, number, number_source) VALUES ('s1', NULL, NULL), ('s2', '0999', 'custom-title')")
        rows = agents_cli.parse(blob(("s1", "0101 · أ", 1, T1), ("s2", "0101 · ب", 2, T1)))
        self.assertEqual(agents_cli.record(self.con, rows)[1], 1)
        got = dict((k, (n, src)) for k, n, src in self.con.execute("SELECT session_key, number, number_source FROM sessions"))
        self.assertEqual(got["s1"], ("0101", "agents"))
        self.assertEqual(got["s2"], ("0999", "custom-title"))

    def test_run_respects_interval_and_failure(self):
        out = blob(("s1", "0101 · أ", 1, T1))
        self.assertEqual(agents_cli.run(self.con, lambda: out)["agents"], 1)
        self.assertEqual(agents_cli.run(self.con, lambda: out), {"agents": "skipped"})
        later = datetime.now(timezone.utc).replace(year=2099)
        self.assertEqual(agents_cli.run(self.con, lambda: "", now=later), {"agents": "empty"})

        def boom():
            raise OSError("x")
        self.assertEqual(agents_cli.run(self.con, boom, now=later), {"agents": "fail"})

    def test_health_counts_restarts_and_age(self):
        self.assertFalse(agents_cli.health(self.con)["healthy"])
        agents_cli.record(self.con, agents_cli.parse(blob(("s1", "0101 · أ", 1, T1))), "2026-10-30T07:00:00Z")
        agents_cli.record(self.con, agents_cli.parse(blob(("s1", "0101 · أ", 2, T1 + 1000), ("s2", "0102 · ب", 3, T1))), "2026-10-30T07:05:00Z")
        h = agents_cli.health(self.con, datetime(2026, 10, 30, 7, 6, tzinfo=timezone.utc))
        self.assertEqual((h["runs"], h["sessions"], h["restarts"], h["last_capture_age_sec"], h["live_at_last_capture"], h["healthy"]), (3, 2, 1, 60, 2, True))
        self.assertFalse(agents_cli.health(self.con, datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc))["healthy"])


if __name__ == "__main__":
    unittest.main()
