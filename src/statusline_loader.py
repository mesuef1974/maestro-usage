"""تحميل data\\statusline_spool.jsonl إلى statusline_samples وplan_snapshots بتكرار آمن.

الأمان: إزاحة بايتات في ingest_state، السطر الناقص يُتجاهل، وفهرس فريد (ts, session_key) يمنع التضاعف
حتى لو أُعيد التحميل من الصفر.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_db  # noqa: E402
import usage_ingest as ui  # noqa: E402
from statusline_collector import SPOOL  # noqa: E402

SPOOL_KEY = "statusline_spool.jsonl"
SAMPLE_COLS = ("ts", "session_key", "context_size", "context_used_pct", "cu_input_tokens", "cu_output_tokens",
               "cu_cache_creation", "cu_cache_read", "cache_hit_ratio", "cache_warm", "cost_usd")


def load_spool(con, spool=None):
    spool = spool or SPOOL
    stats = {"lines": 0, "samples_new": 0, "plans_new": 0, "bad": 0}
    if not os.path.exists(spool):
        return stats
    row = con.execute("SELECT offset_bytes FROM ingest_state WHERE source_path=?", (SPOOL_KEY,)).fetchone()
    offset = row[0] if row else 0
    size = os.path.getsize(spool)
    if size < offset:
        offset = 0
    lines, new_off = ui.read_new_lines(spool, offset)
    with con:
        for line in lines:
            stats["lines"] += 1
            try:
                r = json.loads(line)
                ts = r["ts"]
            except (ValueError, KeyError, TypeError):
                stats["bad"] += 1
                continue
            cur = con.execute(
                "INSERT OR IGNORE INTO statusline_samples(%s) VALUES (%s)" % (",".join(SAMPLE_COLS), ",".join("?" * len(SAMPLE_COLS))),
                tuple(r.get(c) for c in SAMPLE_COLS))
            stats["samples_new"] += cur.rowcount
            if r.get("five_hour_pct") is not None or r.get("seven_day_pct") is not None:
                cur = con.execute(
                    "INSERT OR IGNORE INTO plan_snapshots(ts, session_key, five_hour_pct, five_hour_resets_at, seven_day_pct, "
                    "seven_day_resets_at, source) VALUES (?,?,?,?,?,?, 'statusline')",
                    (ts, r.get("session_key"), r.get("five_hour_pct"), r.get("five_hour_resets_at"),
                     r.get("seven_day_pct"), r.get("seven_day_resets_at")))
                stats["plans_new"] += cur.rowcount
        con.execute(
            "INSERT INTO ingest_state(source_path, offset_bytes, size_bytes, mtime, updated_at, first_ts, session_key) "
            "VALUES (?,?,?,?,?,NULL,NULL) ON CONFLICT(source_path) DO UPDATE SET offset_bytes=excluded.offset_bytes, "
            "size_bytes=excluded.size_bytes, mtime=excluded.mtime, updated_at=excluded.updated_at",
            (SPOOL_KEY, new_off, size, os.path.getmtime(spool), usage_db.now_iso()))
    return stats


if __name__ == "__main__":
    print(json.dumps(load_spool(usage_db.connect()), ensure_ascii=False))
