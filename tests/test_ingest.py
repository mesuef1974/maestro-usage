"""اختبارات المحمّل على بيانات صناعية: التكرار، التزايد، السطر الناقص، التكرار الآمن، الإسناد."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import usage_db  # noqa: E402
import usage_ingest as ui  # noqa: E402
import backup_db  # noqa: E402


def a_line(mid, ts, out=10, model="claude-sonnet-5-5", cr=1000, inp=3, cc=50, sid="s", side=False, cwd="D:\\proj", branch="main"):
    return json.dumps({"type": "assistant", "timestamp": ts, "sessionId": sid, "cwd": cwd, "gitBranch": branch,
                       "isSidechain": side, "requestId": "req_" + mid,
                       "message": {"id": mid, "model": model, "content": [{"type": "text", "text": "نص سري"}],
                                   "usage": {"input_tokens": inp, "cache_creation_input_tokens": cc,
                                             "cache_read_input_tokens": cr, "output_tokens": out,
                                             "output_tokens_details": {"thinking_tokens": 2}}}}, ensure_ascii=False, separators=(",", ":"))


def title_line(t, sid="s"):
    return json.dumps({"type": "custom-title", "customTitle": t, "sessionId": sid}, ensure_ascii=False, separators=(",", ":"))


def write(path, lines, trailing_newline=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + ("\n" if trailing_newline else ""))


def append(path, lines):
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "projects")
        self.db = os.path.join(self.tmp, "u.sqlite3")
        self.con = usage_db.connect(self.db)

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_ingest(self):
        return ui.run(self.con, self.root, app_dir=None)

    def q(self, sql, *a):
        return self.con.execute(sql, a).fetchall()


class TestIngest(Base):
    def test_streaming_duplicates_keep_max_output(self):
        p = os.path.join(self.root, "proj", "aaa.jsonl")
        write(p, [a_line("m1", "2026-10-01T00:00:01Z", out=5), a_line("m1", "2026-10-01T00:00:02Z", out=40),
                  a_line("m1", "2026-10-01T00:00:03Z", out=40), a_line("m2", "2026-10-01T00:00:04Z", out=7)])
        self.run_ingest()
        self.assertEqual(self.q("SELECT COUNT(*) FROM usage_turns")[0][0], 2)
        self.assertEqual(self.q("SELECT output_tokens FROM usage_turns WHERE message_id='m1'")[0][0], 40)
        self.assertEqual(self.q("SELECT thinking_tokens FROM usage_turns WHERE message_id='m1'")[0][0], 2)

    def test_synthetic_excluded_and_counted(self):
        p = os.path.join(self.root, "proj", "aaa.jsonl")
        write(p, [a_line("m1", "2026-10-01T00:00:01Z"), a_line("m2", "2026-10-01T00:00:02Z", model="<synthetic>")])
        st = self.run_ingest()
        self.assertEqual(st["synthetic"], 1)
        self.assertEqual(self.q("SELECT COUNT(*) FROM usage_turns")[0][0], 1)

    def test_idempotent(self):
        p = os.path.join(self.root, "proj", "aaa.jsonl")
        write(p, [a_line("m1", "2026-10-01T00:00:01Z"), a_line("m2", "2026-10-01T00:00:02Z")])
        self.run_ingest()
        snap1 = self.q("SELECT * FROM usage_turns ORDER BY message_id")
        st2 = self.run_ingest()
        self.assertEqual(st2["turns_new"], 0)
        self.assertEqual(st2["files_unchanged"], 1)
        self.assertEqual(snap1, self.q("SELECT * FROM usage_turns ORDER BY message_id"))

    def test_idempotent_after_forced_reread(self):
        p = os.path.join(self.root, "proj", "aaa.jsonl")
        write(p, [a_line("m1", "2026-10-01T00:00:01Z", out=9), a_line("m2", "2026-10-01T00:00:02Z")])
        self.run_ingest()
        snap = self.q("SELECT * FROM usage_turns ORDER BY message_id")
        self.con.execute("UPDATE ingest_state SET offset_bytes=0")
        self.con.commit()
        self.run_ingest()
        self.assertEqual(snap, self.q("SELECT * FROM usage_turns ORDER BY message_id"))

    def test_incremental_append(self):
        p = os.path.join(self.root, "proj", "aaa.jsonl")
        write(p, [a_line("m1", "2026-10-01T00:00:01Z", out=5)])
        self.run_ingest()
        append(p, [a_line("m1", "2026-10-01T00:00:02Z", out=30), a_line("m3", "2026-10-01T00:00:05Z")])
        st = self.run_ingest()
        self.assertEqual(st["turns_new"], 1)
        self.assertEqual(st["turns_updated"], 1)
        self.assertEqual(self.q("SELECT output_tokens FROM usage_turns WHERE message_id='m1'")[0][0], 30)
        self.assertEqual(self.q("SELECT COUNT(*) FROM usage_turns")[0][0], 2)

    def test_partial_last_line_ignored_then_completed(self):
        p = os.path.join(self.root, "proj", "aaa.jsonl")
        full = a_line("m2", "2026-10-01T00:00:02Z")
        write(p, [a_line("m1", "2026-10-01T00:00:01Z")])
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write(full[:40])  # سطر ناقص بلا سطر جديد
        st = self.run_ingest()
        self.assertEqual(st["turns_new"], 1)
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write(full[40:] + "\n")
        st = self.run_ingest()
        self.assertEqual(st["turns_new"], 1)
        self.assertEqual(self.q("SELECT COUNT(*) FROM usage_turns")[0][0], 2)

    def test_file_shrink_resets_without_duplicates(self):
        p = os.path.join(self.root, "proj", "aaa.jsonl")
        write(p, [a_line("m1", "2026-10-01T00:00:01Z"), a_line("m2", "2026-10-01T00:00:02Z"), a_line("m3", "2026-10-01T00:00:03Z")])
        self.run_ingest()
        write(p, [a_line("m1", "2026-10-01T00:00:01Z")])
        st = self.run_ingest()
        self.assertEqual(st["files_reset"], 1)
        self.assertEqual(self.q("SELECT COUNT(*) FROM usage_turns WHERE message_id='m1'")[0][0], 1)

    def test_cross_file_duplicate_goes_to_oldest_file_in_any_order(self):
        old = os.path.join(self.root, "proj", "zzz-old.jsonl")   # أقدم timestamp لكن اسمه لاحق أبجديًّا
        new = os.path.join(self.root, "proj", "aaa-new.jsonl")
        write(old, [a_line("m1", "2026-10-01T00:00:01Z"), a_line("mX", "2026-10-01T00:00:02Z")])
        write(new, [a_line("m0", "2026-10-02T00:00:00Z"), a_line("m1", "2026-10-01T00:00:01Z")])
        self.run_ingest()
        self.assertEqual(self.q("SELECT session_key FROM usage_turns WHERE message_id='m1'")[0][0], "zzz-old")
        self.assertEqual(self.q("SELECT COUNT(*) FROM usage_turns")[0][0], 3)
        # عكس ترتيب التحميل يعطي النتيجة نفسها
        con2 = usage_db.connect(os.path.join(self.tmp, "u2.sqlite3"))
        stats = dict.fromkeys(["files_ingested", "files_unchanged", "files_reset", "lines_read", "synthetic", "bad_lines",
                               "turns_new", "turns_updated", "turns_reassigned", "turns_dup_skipped"], 0)
        for p in (old, new):
            ui.ingest_file(con2, self.root, p, stats)
        self.assertEqual(con2.execute("SELECT session_key FROM usage_turns WHERE message_id='m1'").fetchone()[0], "zzz-old")
        con2.close()

    def test_cross_file_duplicate_prefers_origin_named_by_session_id(self):
        origin = os.path.join(self.root, "proj", "zzz-origin.jsonl")
        fork = os.path.join(self.root, "proj", "aaa-fork.jsonl")  # تفرّع بالتوقيت نفسه واسم أصغر
        line = a_line("m1", "2026-10-01T00:00:01Z", sid="zzz-origin")
        write(origin, [line])
        write(fork, [line])
        for order in ((origin, fork), (fork, origin)):
            con2 = usage_db.connect(os.path.join(self.tmp, "o%d.sqlite3" % (order[0] == fork)))
            stats = dict.fromkeys(["files_ingested", "files_unchanged", "files_reset", "lines_read", "synthetic",
                                   "bad_lines", "turns_new", "turns_updated", "turns_reassigned", "turns_dup_skipped"], 0)
            for p in order:
                ui.ingest_file(con2, self.root, p, stats)
            self.assertEqual(con2.execute("SELECT session_key FROM usage_turns").fetchone()[0], "zzz-origin")
            con2.close()

    def test_turn_origin_follows_last_user_line_across_increments(self):
        p = os.path.join(self.root, "proj", "aaa.jsonl")
        def user(o):
            return json.dumps({"type": "user", "turnOrigin": o, "message": {"content": "نص لا يُحفظ"}},
                              ensure_ascii=False, separators=(",", ":"))
        write(p, [user("human"), a_line("m1", "2026-10-01T00:00:01Z"), user("scheduled"), a_line("m2", "2026-10-01T00:00:02Z")])
        self.run_ingest()
        append(p, [a_line("m3", "2026-10-01T00:00:03Z"), user("peer"), a_line("m4", "2026-10-01T00:00:04Z")])
        self.run_ingest()
        got = dict(self.q("SELECT message_id, turn_origin FROM usage_turns"))
        self.assertEqual(got, {"m1": "human", "m2": "scheduled", "m3": "scheduled", "m4": "peer"})

    def test_cache_creation_ttl_split_stored_and_null_when_absent(self):
        p = os.path.join(self.root, "proj", "aaa.jsonl")
        with_ttl = json.loads(a_line("m1", "2026-10-01T00:00:01Z", cc=300))
        with_ttl["message"]["usage"]["cache_creation"] = {"ephemeral_1h_input_tokens": 200, "ephemeral_5m_input_tokens": 100}
        broken = json.loads(a_line("m3", "2026-10-01T00:00:03Z"))
        broken["message"]["usage"]["cache_creation"] = "غير قاموس"
        def dump(d):
            return json.dumps(d, ensure_ascii=False, separators=(",", ":"))
        write(p, [dump(with_ttl), a_line("m2", "2026-10-01T00:00:02Z"), dump(broken)])
        self.run_ingest()
        got = {r[0]: (r[1], r[2]) for r in self.q("SELECT message_id, cc_1h, cc_5m FROM usage_turns")}
        self.assertEqual(got, {"m1": (200, 100), "m2": (None, None), "m3": (None, None)})
        self.run_ingest()
        self.assertEqual(self.q("SELECT cc_1h, cc_5m FROM usage_turns WHERE message_id='m1'")[0], (200, 100))

    def test_mixed_session_id_group_is_stable_across_rereads(self):
        fa = os.path.join(self.root, "proj", "aaa.jsonl")
        fb = os.path.join(self.root, "proj", "bbb.jsonl")
        write(fa, [a_line("m1", "2026-10-01T00:00:01Z", sid="other")])
        write(fb, [a_line("m1", "2026-10-01T00:00:01Z", sid="ccc")])
        self.run_ingest()
        first = self.q("SELECT session_key, sid_rank FROM usage_turns")
        for _ in range(3):
            self.con.execute("UPDATE ingest_state SET offset_bytes=0")
            self.con.commit()
            st = self.run_ingest()
            self.assertEqual(st["turns_reassigned"], 0)
        self.assertEqual(first, self.q("SELECT session_key, sid_rank FROM usage_turns"))

    def test_subagent_attributed_to_parent_session(self):
        p = os.path.join(self.root, "proj", "parent-id", "subagents", "agent-1.jsonl")
        write(p, [a_line("m1", "2026-10-01T00:00:01Z", side=True)])
        self.run_ingest()
        self.assertEqual(self.q("SELECT session_key, is_sidechain FROM usage_turns")[0], ("parent-id", 1))

    def test_number_from_last_custom_title(self):
        p = os.path.join(self.root, "proj", "aaa.jsonl")
        write(p, [title_line("0101 · أولى"), a_line("m1", "2026-10-01T00:00:01Z"), title_line("0102 · ثانية"), title_line("بلا رقم")])
        self.run_ingest()
        self.assertEqual(self.q("SELECT number, number_source, title FROM sessions")[0], ("0102", "custom-title", None))

    def test_number_from_app_fallback_only_when_missing(self):
        app = os.path.join(self.tmp, "app", "a", "b")
        os.makedirs(app)
        for name, cli, title in (("local_1.json", "aaa", "0440 · x"), ("local_2.json", "bbb", "0999 · y")):
            with open(os.path.join(app, name), "w", encoding="utf-8") as f:
                json.dump({"cliSessionId": cli, "title": title, "extra": "لا يُقرأ"}, f, ensure_ascii=False, separators=(",", ":"))
        write(os.path.join(self.root, "proj", "aaa.jsonl"), [a_line("m1", "2026-10-01T00:00:01Z")])
        write(os.path.join(self.root, "proj", "bbb.jsonl"), [title_line("0104 · z"), a_line("m2", "2026-10-01T00:00:02Z")])
        ui.run(self.con, self.root, app_dir=os.path.join(self.tmp, "app"))
        got = dict((r[0], r[1:]) for r in self.q("SELECT session_key, number, number_source FROM sessions"))
        self.assertEqual(got["aaa"], ("0440", "app"))
        self.assertEqual(got["bbb"], ("0104", "custom-title"))

    def test_no_text_stored_anywhere(self):
        p = os.path.join(self.root, "proj", "aaa.jsonl")
        write(p, [title_line("0101 · قطعة٧٧٧فريدة"), a_line("m1", "2026-10-01T00:00:01Z")])
        self.run_ingest()
        self.con.close()
        raw = open(self.db, "rb").read()
        self.assertNotIn("قطعة٧٧٧".encode("utf-8"), raw)
        self.con = usage_db.connect(self.db)

    def test_backup_integrity(self):
        write(os.path.join(self.root, "proj", "aaa.jsonl"), [a_line("m1", "2026-10-01T00:00:01Z")])
        self.run_ingest()
        dest, res = backup_db.backup(self.db, os.path.join(self.tmp, "bk"))
        self.assertEqual(res, "ok")
        self.assertTrue(os.path.exists(dest))


if __name__ == "__main__":
    unittest.main()
