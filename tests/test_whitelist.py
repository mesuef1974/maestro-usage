"""القائمة البيضاء للحقول النصية: لا نص حر في أي جدول. يعمل على قاعدة صناعية، ويُشغَّل على القاعدة الحقيقية بالمتغيّر MAESTRO_CHECK_REAL=1."""
import os
import re
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import usage_db  # noqa: E402
import usage_ingest as ui  # noqa: E402
from test_ingest import a_line, title_line, write  # noqa: E402

ID = r"[A-Za-z0-9_\-:.]{1,100}"
PATH = r"[A-Za-z]:[\\/][^\r\n\t]{0,300}|/[^\r\n\t]{0,300}"
# (جدول، عمود) ← تعبير يجب أن يطابق القيمة كاملةً. NULL مسموح دائمًا.
WHITELIST = {
    ("sessions", "session_key"): ID,
    ("sessions", "number"): r"\d{4}",
    ("sessions", "number_source"): r"custom-title|app|agents",
    ("sessions", "cwd"): PATH,
    ("sessions", "branch"): r"[^\s]{1,200}",
    ("sessions", "first_seen"): r"\d{4}-\d\d-\d\dT[\d:.]+Z",
    ("sessions", "last_seen"): r"\d{4}-\d\d-\d\dT[\d:.]+Z",
    ("usage_turns", "message_id"): ID,
    ("usage_turns", "session_key"): ID,
    ("usage_turns", "ts"): r"\d{4}-\d\d-\d\dT[\d:.]+Z",
    ("usage_turns", "model"): r"[A-Za-z0-9._\-]{1,60}",
    ("usage_turns", "request_id"): ID,
    ("usage_turns", "turn_origin"): r"[a-z_]{1,30}",
    ("ingest_state", "last_origin"): r"[a-z_]{1,30}",
    ("usage_turns", "source_path"): r"[^\r\n\t]{1,400}\.jsonl",
    ("ingest_state", "source_path"): r"[^\r\n\t]{1,400}\.jsonl",
    ("ingest_state", "updated_at"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("ingest_state", "first_ts"): r"\d{4}-\d\d-\d\dT[\d:.]+Z",
    ("ingest_state", "session_key"): ID,
    ("usage_rollups", "grain"): r"day|week|month",
    ("usage_rollups", "period_start"): r"\d{4}-\d\d-\d\d",
    ("models", "name"): r"[A-Za-z0-9._\-]{1,60}",
    ("models", "family"): r"sonnet|opus|haiku|fable",
    ("models", "first_seen"): r"\d{4}-\d\d-\d\dT[\d:.]+Z",
    ("models", "last_seen"): r"\d{4}-\d\d-\d\dT[\d:.]+Z",
    ("usage_rollups", "refreshed_at"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("schema_version", "applied_at"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("plan_snapshots", "ts"): r"[\d\-T:.Z]+",
    ("plan_snapshots", "session_key"): ID,
    ("plan_snapshots", "five_hour_resets_at"): r"[\d\-T:.Z]+",
    ("plan_snapshots", "seven_day_resets_at"): r"[\d\-T:.Z]+",
    ("plan_snapshots", "source"): r"statusline|get_usage|cli_usage",
    ("plan_snapshots", "fable_resets_at"): r"[\d\-T:.Z]+",
    ("cli_usage_counts", "ts"): r"[\d\-T:.Z]+",
    ("cli_usage_counts", "window"): r"24h|7d",
    ("plan_snapshots", "plan"): r"[A-Za-z0-9 _\-]{1,30}",
    ("statusline_samples", "ts"): r"[\d\-T:.Z]+",
    ("statusline_samples", "session_key"): ID,
    # config_changes: مفتاح/قيمتان قصيرتان تكتبها 0101؛ الملاحظة نص بشري قصير من المالك لا من السجلات
    ("agent_starts", "session_id"): ID,
    ("agent_starts", "started_at"): r"\d{4}-\d\d-\d\dT[\d:.]+Z",
    ("agent_starts", "number"): r"\d{4}",
    ("agent_starts", "kind"): r"[a-z_\-]{1,30}",
    ("agent_starts", "first_seen"): r"\d{4}-\d\d-\d\dT[\d:.]+Z",
    ("agent_starts", "last_seen"): r"\d{4}-\d\d-\d\dT[\d:.]+Z",
    ("storage_scans", "ts"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("storage_dirs", "ts"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("storage_dirs", "kind"): r"top|proj|ext",
    ("storage_dirs", "name"): r"[^\r\n\t]{1,200}",  # اسم مجلد أو امتداد، لا اسم ملف
    ("storage_dirs", "newest"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("storage_dirs", "oldest"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("storage_actions", "ts"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("storage_actions", "action"): r"quarantine|restore|purge",
    ("storage_actions", "grp"): r"[a-z_]{1,40}",
    ("storage_actions", "qdir"): PATH,
    ("storage_actions", "status"): r"quarantined|restored|purged|done",
    ("startup_samples", "session_key"): ID,
    ("startup_samples", "ts"): r"\d{4}-\d\d-\d\dT[\d:.]+Z",
    ("startup_samples", "model"): r"[A-Za-z0-9._\-]{1,60}",
    ("startup_samples", "origin"): r"[a-z_]{1,30}",
    ("startup_samples", "folder"): r"[^\r\n\t]{1,200}",
    ("startup_samples", "proj"): r"[^\r\n\t/\\]{1,300}",
    ("startup_samples", "cc_version"): r"[0-9A-Za-z.\-]{1,30}",
    ("config_fingerprints", "ts"): r"\d{4}-\d\d-\d\dT[\d:.]+Z",
    ("config_fingerprints", "item"): r"[^\r\n\t]{1,300}",
    ("config_fingerprints", "sha"): r"[0-9a-f]{64}",
    ("project_repos", "repo"): r"[A-Za-z0-9_.\-]{1,60}/[A-Za-z0-9_.\-]{1,60}",
    ("project_repos", "visibility"): r"public|private",
    ("project_repos", "role"): r"platform|docs|automation|backup",
    ("project_repos", "local_dir"): PATH,
    ("config_changes", "ts"): r"[\d\-T:.Z]+",
    ("config_changes", "key"): r"[A-Za-z0-9_]{1,80}",
    ("config_changes", "old_value"): r"[^\r\n]{1,80}",
    ("config_changes", "new_value"): r"[^\r\n]{1,80}",
    ("config_changes", "note"): r".{0,200}",
    # تاريخ الأتمتة: معرّفات وتصنيفات وأوقات، ونصوص البطاقات تبقى في الدفتر
    ("auto_cards", "card_id"): ID,
    ("auto_cards", "era"): r"auto|manual",
    ("auto_cards", "source"): r"[a-z_0-9]{1,30}",
    ("auto_cards", "req_type_key"): r"[a-z]{1,12}",
    ("auto_cards", "size_key"): r"[a-z]{1,12}",
    ("auto_cards", "priority"): r"P\d",
    ("auto_cards", "approval_key"): r"[a-z]{1,12}",
    ("auto_cards", "state"): r"[a-z_]{1,30}",
    ("auto_cards", "created_ts"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("auto_cards", "first_run_ts"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("auto_cards", "pr_ts"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("auto_cards", "merged_ts"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("auto_cards", "ended_ts"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("auto_cards", "last_ts"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("auto_cards", "stop_key"): r"[a-z]{1,12}",
    ("auto_events", "card_id"): ID,
    ("auto_events", "ts"): r"\d{4}-\d\d-\d\dT[\d:]+Z",
    ("auto_events", "kind"): r"created|state|update|note|approval",
    ("auto_events", "state"): r"[a-z_]{1,30}",
    ("auto_events", "op"): r"run|ci|review",
    ("auto_events", "model"): r"haiku|sonnet|opus|fable",
    ("auto_sync", "synced_at"): r"\d{4}-\d\d-\d\dT[\d:.]+Z",
}
# أعمدة يجب أن تكون NULL دومًا (لا نصوص)
ALWAYS_NULL = {("sessions", "title")}


def text_columns(con):
    for (tbl,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
        for _cid, name, ctype, *_ in con.execute("PRAGMA table_info(%s)" % tbl).fetchall():
            if (ctype or "").upper() == "TEXT":
                yield tbl, name


class TestWhitelist(unittest.TestCase):
    def check(self, con):
        for tbl, col in text_columns(con):
            if (tbl, col) in ALWAYS_NULL:
                n = con.execute("SELECT COUNT(*) FROM %s WHERE %s IS NOT NULL" % (tbl, col)).fetchone()[0]
                self.assertEqual(n, 0, "%s.%s يجب أن يبقى NULL" % (tbl, col))
                continue
            self.assertIn((tbl, col), WHITELIST, "عمود نصي جديد بلا قاعدة بيضاء: %s.%s" % (tbl, col))
            rx = re.compile(WHITELIST[(tbl, col)], re.S)
            bad = 0
            for (v,) in con.execute("SELECT DISTINCT %s FROM %s WHERE %s IS NOT NULL" % (col, tbl, col)):
                if not rx.fullmatch(str(v)):
                    bad += 1
            self.assertEqual(bad, 0, "قيم خارج القائمة البيضاء في %s.%s: %d" % (tbl, col, bad))

    def test_synthetic_db(self):
        tmp = tempfile.mkdtemp()
        try:
            root = os.path.join(tmp, "p")
            write(os.path.join(root, "proj", "aaa.jsonl"),
                  [title_line("0101 · عنوان فيه بيانات"), a_line("m1", "2026-10-01T00:00:01Z", branch="feat/x-1")])
            write(os.path.join(root, "proj", "par", "subagents", "agent-9.jsonl"), [a_line("m2", "2026-10-01T00:00:02Z", side=True)])
            con = usage_db.connect(os.path.join(tmp, "u.sqlite3"))
            ui.run(con, root, app_dir=None)
            self.check(con)
            con.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @unittest.skipUnless(os.environ.get("MAESTRO_CHECK_REAL"), "للقاعدة الحقيقية فقط")
    def test_real_db(self):
        con = usage_db.connect(os.environ.get("MAESTRO_USAGE_DB"))
        self.check(con)


if __name__ == "__main__":
    unittest.main()
