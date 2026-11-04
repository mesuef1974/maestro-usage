"""استيراد أدوار جلسة من خارج ~/.claude/projects (جلسات سحابية) إلى usage_turns، أرقام فقط.

الملف jsonl سطرٌ لكل دور: message_id وts وmodel والحقول الأربعة. يُنتجه scripts/export_transcript_numbers.py.
متكرّر الأمان: INSERT OR IGNORE على message_id، وإعادته لا تضاعف الصفوف. لا نصوص: القيم تُفحص بقائمة بيضاء قبل الكتابة.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_db  # noqa: E402

ID = re.compile(r"[A-Za-z0-9_\-:.]{1,100}")
TS = re.compile(r"\d{4}-\d\d-\d\dT[\d:.]+Z")
MODEL = re.compile(r"[A-Za-z0-9._\-]{1,60}")
INTS = ("input_tokens", "cache_creation_tokens", "cache_read_tokens", "output_tokens")


def import_file(con, path, session_key, label="cloud"):
    """يعيد (جديد، مكرّر، مرفوض)."""
    if not ID.fullmatch(session_key) or not ID.fullmatch(label):
        raise ValueError("معرّف الجلسة أو الوسم غير صالح")
    new = dup = bad = 0
    first = last = None
    with open(path, encoding="utf-8") as f, con:
        for ln in f:
            try:
                d = json.loads(ln)
                ok = (ID.fullmatch(str(d["message_id"])) and TS.fullmatch(str(d["ts"])) and MODEL.fullmatch(str(d["model"]))
                      and all(isinstance(d[k], int) and d[k] >= 0 for k in INTS))
            except (ValueError, KeyError, TypeError):
                ok = False
            if not ok:
                bad += 1
                continue
            first = min(first or d["ts"], d["ts"])
            last = max(last or d["ts"], d["ts"])
            _ensure_session(con, session_key, d["ts"])
            cur = con.execute(
                "INSERT OR IGNORE INTO usage_turns(message_id, session_key, ts, model, input_tokens, cache_creation_tokens, "
                "cache_read_tokens, output_tokens, source_path) VALUES (?,?,?,?,?,?,?,?,?)",
                (d["message_id"], session_key, d["ts"], d["model"], d["input_tokens"], d["cache_creation_tokens"],
                 d["cache_read_tokens"], d["output_tokens"], "external:" + label))
            if cur.rowcount:
                new += 1
            else:
                dup += 1
        if first:
            con.execute("UPDATE sessions SET first_seen = MIN(COALESCE(first_seen, ?), ?), last_seen = MAX(COALESCE(last_seen, ?), ?) "
                        "WHERE session_key = ?", (first, first, last, last, session_key))
    return new, dup, bad


EXTERNAL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "external")


def run_dir(con, directory=None):
    """يستورد كل data/external/<معرّف الجلسة>.jsonl الجديد أو المتغيّر (بصمة الحجم والزمن في ingest_state). يعيد عدد الأدوار الجديدة."""
    d = directory or EXTERNAL_DIR
    total = 0
    if not os.path.isdir(d):
        return 0
    for name in sorted(os.listdir(d)):
        if not name.endswith(".jsonl"):
            continue
        path = os.path.join(d, name)
        st = os.stat(path)
        key = "external/" + name
        row = con.execute("SELECT size_bytes, mtime FROM ingest_state WHERE source_path = ?", (key,)).fetchone()
        if row and row[0] == st.st_size and row[1] == st.st_mtime:
            continue
        try:
            new, _dup, _bad = import_file(con, path, name[:-6])
        except ValueError:
            continue  # اسم ملف غير صالح معرّفًا: يُتجاهل
        total += new
        con.execute("INSERT INTO ingest_state(source_path, offset_bytes, size_bytes, mtime, updated_at) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(source_path) DO UPDATE SET offset_bytes=excluded.offset_bytes, size_bytes=excluded.size_bytes, "
                    "mtime=excluded.mtime, updated_at=excluded.updated_at", (key, st.st_size, st.st_size, st.st_mtime, usage_db.now_iso()))
        con.commit()
    return total


def _ensure_session(con, key, ts):
    con.execute("INSERT OR IGNORE INTO sessions(session_key, first_seen, last_seen) VALUES (?,?,?)", (key, ts, ts))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file")
    ap.add_argument("--session", required=True)
    ap.add_argument("--label", default="cloud")
    a = ap.parse_args(argv)
    con = usage_db.connect()
    print("جديد %d · مكرّر %d · مرفوض %d" % import_file(con, a.file, a.session, a.label))
    return 0


if __name__ == "__main__":
    sys.exit(main())
