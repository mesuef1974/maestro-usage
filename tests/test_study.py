"""اختبار جدول الدراسة اليومي على قاعدة صناعية بأرقام معروفة."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import study  # noqa: E402
import usage_db  # noqa: E402


class TestStudy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = usage_db.connect(os.path.join(self.tmp, "u.sqlite3"))
        c = self.con
        c.execute("INSERT INTO sessions(session_key, number, cwd) VALUES ('aaaaaaaa1','0101','D:/x'),('bbbbbbbb2',NULL,'D:/y')")

        def t(i, s, ts, cc, cr, u=1, side=0, org="human"):
            c.execute("INSERT INTO usage_turns(message_id,session_key,ts,model,input_tokens,cache_creation_tokens,cache_read_tokens,"
                      "output_tokens,thinking_tokens,is_sidechain,source_path,turn_origin) VALUES (?,?,?,?,1,?,?,?,0,?,'p.jsonl',?)",
                      (i, s, ts, "claude-sonnet-5-5", cc, cr, u, side, None if side else org))
        t("1", "aaaaaaaa1", "2026-10-20T01:00:00Z", 0, 290_000)
        t("2", "aaaaaaaa1", "2026-10-20T01:05:00Z", 0, 293_000, org="peer")
        t("3", "aaaaaaaa1", "2026-10-20T01:06:00Z", 0, 40_000)              # هبوط من 293001 (مستوى الضغط)
        t("4", "aaaaaaaa1", "2026-10-20T04:00:00Z", 7000, 40_000)           # إيقاظ بعد ساعتين ونصف
        t("5", "aaaaaaaa1", "2026-10-20T04:01:00Z", 0, 5_000, side=1)       # وكيل فرعي لا يدخل الخيط الرئيس
        t("6", "bbbbbbbb2", "2026-10-21T01:00:00Z", 0, 10_000)
        c.commit()
        self.rows = {r["day"]: r for r in study.daily(c)}

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_day_totals_and_per_reply(self):
        r = self.rows["2026-10-20"]
        self.assertEqual((r["replies"], r["main"], r["cr"], r["cc"]), (5, 4, 290_000 + 293_000 + 40_000 + 40_000 + 5_000, 7000))
        self.assertEqual(r["cr_per_reply"], round(r["cr"] / 5))
        self.assertEqual((r["sessions"], r["roles"], r["human"]), (1, 1, 3))
        self.assertEqual(r["peer_pct"], 25.0)

    def test_wake_drop_and_level(self):
        r = self.rows["2026-10-20"]
        self.assertEqual((r["wake"], r["wake_cc"]), (1, 7000))
        self.assertEqual((r["drops"], r["level_med"]), (1, 293_001))
        self.assertEqual(r["max_ctx"], 293_001)

    def test_unnumbered_session_not_a_project_role(self):
        r = self.rows["2026-10-21"]
        self.assertEqual((r["sessions"], r["roles"]), (1, 0))

    def test_first_filter(self):
        self.assertEqual([r["day"] for r in study.daily(self.con, "2026-10-21")], ["2026-10-21"])

    def _write(self, name, lines):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n")
        return path

    def test_ledger_done_counts_card_once_at_first_completion(self):
        path = self._write("events.jsonl", [
            {"ts": "2026-10-20T02:00:00+03:00", "id": "A", "kind": "state", "data": {"state": "approved"}},
            {"ts": "2026-10-20T23:30:00-03:00", "id": "A", "kind": "state", "data": {"state": "merged"}},   # 02:30Z من 10-21
            {"ts": "2026-10-22T10:00:00+03:00", "id": "A", "kind": "state", "data": {"state": "published"}},
            {"ts": "2026-10-20T12:00:00+03:00", "id": "B", "kind": "state", "data": {"state": "closed"}},
            {"ts": "2026-10-20T12:00:00+03:00", "id": "B", "kind": "note", "data": {"text": "merged"}}])
        self.assertEqual(study.ledger_done(path), {"2026-10-21": 1, "2026-10-20": 1})
        self.assertEqual(study.ledger_done(os.path.join(self.tmp, "missing.jsonl")), {})

    def test_wake_events_count_messages_between_replies(self):
        os.makedirs(os.path.join(self.tmp, "inbox"))
        self._write(os.path.join("inbox", "0101.jsonl"), [
            {"k": "msg", "id": 1, "ts": "2026-10-20T05:00:00+03:00", "from": "0440", "text": "x"},   # 02:00Z
            {"k": "ack", "id": 1, "ts": "2026-10-20T05:00:00+03:00"},
            {"k": "msg", "id": 2, "ts": "2026-10-20T06:30:00+03:00", "from": "0440", "text": "y"},   # 03:30Z
            {"k": "msg", "id": 3, "ts": "2026-10-20T08:00:00+03:00", "from": "0440", "text": "z"}])  # 05:00Z بعد الإيقاظ
        self._write(os.path.join("inbox", "9999.jsonl"), [])
        inbox = study.inbox_times(os.path.join(self.tmp, "inbox"))
        self.assertEqual(sorted(inbox), ["0101"])
        w = study.wake_events(self.con, inbox)
        self.assertEqual([(x["day"], x["role"], x["cc"], x["msgs"]) for x in w], [("2026-10-20", "0101", 7000, 2)])
        b = {r["bucket"]: r for r in study.wake_by_msgs(w, "2026-10-20")}
        self.assertEqual((b["2-3"]["wakes"], b["2-3"]["cc_mean"], b["0"]["wakes"]), (1, 7000, 0))

    def test_snapshot_cost_matches_short_unnumbered_session_with_a_snapshot(self):
        self.con.execute("INSERT INTO plan_snapshots(ts, source) VALUES ('2026-10-21T01:00:30Z', 'get_usage')")
        self.con.commit()
        self.assertEqual(study.snapshot_cost(self.con), {"2026-10-21": (1, 1 + 10_000 + 1)})

    def test_events_from_config_changes_and_counter_reset(self):
        self.con.execute("INSERT INTO config_changes(ts, key, old_value, new_value, note) VALUES ('2026-10-29','K','a','b','n')")
        self.con.commit()
        counter = self._write("c.json", [{"started": "2026-10-23 08:12", "sessions": {
            "0101": {"since": "2026-10-29 17:27"}, "0301": {"since": "2026-10-23 08:12"}}}])
        ev = study.events(self.con, counter)
        self.assertIn("K: a→b", ev["2026-10-29"])
        self.assertTrue(ev["2026-10-29"].endswith("تصفير عدّاد 0101 14:27Z"))
        self.assertNotIn("0301", ev["2026-10-29"])

    def test_git_commits_are_distinct_across_branches_and_use_utc(self):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(repo)

        def git(*a, date=None):
            env = dict(os.environ, GIT_COMMITTER_DATE=date or "", GIT_AUTHOR_DATE=date or "")
            subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, env=env,
                           capture_output=True)
        git("init", "-q", "-b", "main")
        git("commit", "--allow-empty", "-qm", "a", date="2026-10-20T23:30:00-03:00")          # 02:30Z من 10-21
        git("checkout", "-qb", "side")
        git("commit", "--allow-empty", "-qm", "b", date="2026-10-20T10:00:00+00:00")
        self.assertEqual(study.git_commits(repo), {"2026-10-21": 1, "2026-10-20": 1})
        self.assertEqual(study.git_commits(os.path.join(self.tmp, "nope")), {})

    def test_enrich_separates_commits_and_cards(self):
        rows = [dict(day="2026-10-20", cr=1000)]
        study.enrich(rows, {"shschool": {"2026-10-20": 2}, "dmw": {"2026-10-20": 3}}, {"2026-10-20": 4},
                     {"0101": []}, [], {}, {"2026-10-20": "e"})
        r = rows[0]
        self.assertEqual((r["commits_shschool"], r["commits_dmw"], r["cards_done"]), (2, 3, 4))
        self.assertEqual((r["cr_per_commit"], r["cr_per_card"], r["event"]), (200, 250, "e"))
        rows = [dict(day="2026-10-21", cr=1000)]
        study.enrich(rows, {}, {}, {}, [], {}, {})
        self.assertEqual((rows[0]["cr_per_commit"], rows[0]["cr_per_card"]), ("", ""))


if __name__ == "__main__":
    unittest.main()
