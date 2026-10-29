"""اتصال قاعدة الاستهلاك وتهيئتها. نصوص القاعدة معرّفات وأرقام فقط."""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("MAESTRO_USAGE_DB", r"C:\Users\mesue\.maestro\flow_usage.sqlite3"))
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "schema.sql"
SCHEMA_VERSION = 3

# بذور config_changes (قرارات المالك في 2026-10-29)؛ الوقت اليوم فقط لأن الساعة غير معروفة.
CONFIG_SEEDS = [
    ("2026-10-29", "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "9", "45", "عتبة الضغط التلقائي؛ التغيير الأول في اليوم"),
    ("2026-10-29", "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "45", "25", "عتبة الضغط التلقائي؛ التغيير الثاني في اليوم نفسه"),
    ("2026-10-29", "statusLine", "none", "command", "ثبّتته 0101 بإذن المالك؛ يسري على الجلسات الجديدة"),
]


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path=None):
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    init_schema(con)
    return con


def _migrate_v2(con):
    """الإصدارات 2-3: turn_origin وsid_rank في usage_turns وlast_origin في ingest_state (لقواعد أُنشئت بالإصدار 1)."""
    for table, col, ctype in (("usage_turns", "turn_origin", "TEXT"), ("ingest_state", "last_origin", "TEXT"),
                              ("usage_turns", "sid_rank", "INTEGER")):
        cols = [r[1] for r in con.execute("PRAGMA table_info(%s)" % table)]
        if cols and col not in cols:
            con.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, ctype))


def init_schema(con):
    _migrate_v2(con)  # قبل السكربت: لا شيء يحدث على قاعدة جديدة (الجداول غير موجودة بعد)
    con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _migrate_v2(con)
    con.execute("INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (?, ?)", (SCHEMA_VERSION, now_iso()))
    con.executemany(
        "INSERT OR IGNORE INTO config_changes(ts, key, old_value, new_value, note) VALUES (?,?,?,?,?)", CONFIG_SEEDS)
    con.commit()
