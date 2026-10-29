"""تعبئة رجعية لعمودي cc_1h وcc_5m في usage_turns من السجلات الأقدم (التي استُوعبت قبل إضافتهما).

يمسّ الأسطر التي تحمل ephemeral_1h فقط، وللملفات الأحدث من --since؛ آمن للإعادة (لا يكتب إلا حيث cc_1h فارغ).
لا يُحفظ أي نص: تُقرأ أرقام cache_creation ومعرّف الرسالة فقط.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_db  # noqa: E402
from usage_ingest import PROJECTS  # noqa: E402

NEEDLE = b"ephemeral_1h"


def iter_files(root, since_epoch):
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".jsonl"):
                p = os.path.join(dirpath, f)
                if os.path.getmtime(p) >= since_epoch:
                    yield p


def file_rows(path):
    """(message_id, cc_1h, cc_5m) لكل رد في الملف يحمل التقسيم؛ التكرار يحتفظ بآخر قيمة."""
    out = {}
    with open(path, "rb") as fh:
        for raw in fh:
            if NEEDLE not in raw:
                continue
            try:
                d = json.loads(raw)
                m = d["message"]
                ttl = m["usage"]["cache_creation"]
                out[m["id"]] = (ttl.get("ephemeral_1h_input_tokens"), ttl.get("ephemeral_5m_input_tokens"))
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
    return [(mid, a, b) for mid, (a, b) in out.items()]


def run(con, root, since_epoch):
    files = rows = updated = 0
    for p in iter_files(root, since_epoch):
        files += 1
        batch = file_rows(p)
        rows += len(batch)
        for mid, a, b in batch:
            cur = con.execute("UPDATE usage_turns SET cc_1h=?, cc_5m=? WHERE message_id=? AND cc_1h IS NULL", (a, b, mid))
            updated += cur.rowcount
        con.commit()
    return files, rows, updated


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=PROJECTS)
    ap.add_argument("--db", default=None)
    ap.add_argument("--since", default="2026-10-09", help="تاريخ UTC (YYYY-MM-DD) لأقدم ملف يُمسح بحسب mtime")
    a = ap.parse_args(argv)
    since = datetime.strptime(a.since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    con = usage_db.connect(a.db)
    t0 = time.time()
    files, rows, updated = run(con, a.root, since)
    left = con.execute("SELECT COUNT(*) FROM usage_turns WHERE cc_1h IS NULL AND ts >= ?", (a.since,)).fetchone()[0]
    print("files=%d rows_with_split=%d updated=%d still_null_since=%d secs=%.0f" % (files, rows, updated, left, time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
