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
    ("sessions", "number_source"): r"custom-title|app",
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
    ("config_changes", "ts"): r"[\d\-T:.Z]+",
    ("config_changes", "key"): r"[A-Za-z0-9_]{1,80}",
    ("config_changes", "old_value"): r"[^\r\n]{1,80}",
    ("config_changes", "new_value"): r"[^\r\n]{1,80}",
    ("config_changes", "note"): r".{0,200}",
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
