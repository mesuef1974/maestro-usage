"""تحميل تزايدي لسجلات Claude Code إلى القاعدة. أرقام ومعرّفات فقط: لا يُحفظ أي نص محادثة.

القواعد (من المرحلة 0):
- التفريد عالمي بـmessage_id؛ الردّ المكرّر داخل الملف يحتفظ بأكبر output_tokens.
- الردّ المكرّر بين ملفات (استئناف/تفرّع ينسخ التاريخ) يُسنَد بالترتيب: الملف الذي اسمه هو sessionId الوارد في السطر (الأصل)،
  ثم أقدم أول timestamp للملف، ثم أصغر مسار. (الاكتشاف: أول timestamp وحده يتعادل في 99.99% من المكرّرات.)
- النموذج <synthetic> يُستبعد ويُعدّ.
- الرقم من آخر custom-title في السجل أولًا، ثم من ملفات التطبيق احتياطًا (number_source).
"""
import argparse
import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_db  # noqa: E402

PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")
APP_SESSIONS = os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude-code-sessions")
NUM_RE = re.compile(r"^\s*(\d{4})\b")
SYNTHETIC = "<synthetic>"
ORIGIN_RE = re.compile(r'"turnOrigin":"([a-z_]{1,30})"')


def iter_logs(root):
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            if f.endswith(".jsonl"):
                yield os.path.join(dp, f)


def owner_key(root, path):
    """الجلسة المالكة: اسم الملف للسجل الرئيس، والمجلد الأب لـsubagents للوكيل الفرعي."""
    parts = os.path.relpath(path, root).split(os.sep)
    if "subagents" in parts:
        return parts[parts.index("subagents") - 1]
    return parts[-1][:-len(".jsonl")]


def read_new_lines(path, offset):
    """يرجع (أسطر كاملة، الإزاحة الجديدة). السطر الناقص في آخر الملف يُتجاهل."""
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read()
    end = data.rfind(b"\n")
    if end < 0:
        return [], offset
    return data[:end + 1].decode("utf-8", errors="replace").splitlines(), offset + end + 1


def first_timestamp(lines):
    for line in lines:
        if '"timestamp"' not in line:
            continue
        try:
            ts = json.loads(line).get("timestamp")
        except ValueError:
            continue
        if isinstance(ts, str):
            return ts
    return None


def parse_lines(lines, origin=None):
    """يلخّص السطور الجديدة: أفضل سطر لكل message_id وآخر رقم عنوان. بلا نصوص."""
    best, number, synthetic, bad = {}, None, 0, 0
    for line in lines:
        # الفحص النصي للسرعة فقط؛ سطر المستخدم الذي يحوي أيضًا نص ردّ (نسخ أو اقتباس) يُحسم بعد تحليل JSON لا بالنص
        maybe = '"type":"assistant"' in line or '"type":"custom-title"' in line
        if '"type":"user"' in line and not maybe:
            m = ORIGIN_RE.search(line)
            if m:
                origin = m.group(1)
            continue
        if not maybe:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if o.get("type") == "user":
            m = ORIGIN_RE.search(line)
            if m:
                origin = m.group(1)
            continue
        if o.get("type") == "custom-title":
            m = NUM_RE.match(o.get("customTitle") or "")
            number = m.group(1) if m else number
            continue
        if o.get("type") != "assistant":
            continue
        msg = o.get("message") or {}
        mid, ts = msg.get("id"), o.get("timestamp")
        if not mid or not ts:
            continue
        model = msg.get("model") or ""
        if model == SYNTHETIC:
            synthetic += 1
            continue
        u = msg.get("usage") or {}
        det = u.get("output_tokens_details")
        ttl = u.get("cache_creation")
        ttl = ttl if isinstance(ttl, dict) else {}
        rec = dict(ts=ts, model=model, inp=u.get("input_tokens") or 0,
                   cc1h=ttl.get("ephemeral_1h_input_tokens"), cc5m=ttl.get("ephemeral_5m_input_tokens"),
                   cc=u.get("cache_creation_input_tokens") or 0, cr=u.get("cache_read_input_tokens") or 0,
                   out=u.get("output_tokens") or 0,
                   think=(det.get("thinking_tokens") or 0) if isinstance(det, dict) else 0,
                   side=1 if o.get("isSidechain") else 0, req=o.get("requestId"),
                   cwd=o.get("cwd"), branch=o.get("gitBranch"), sid=o.get("sessionId"), origin=origin)
        if mid not in best or rec["out"] >= best[mid]["out"]:
            best[mid] = rec
    return best, number, synthetic, bad, origin


def ingest_file(con, root, path, stats):
    rel = os.path.relpath(path, root)
    st = os.stat(path)
    row = con.execute("SELECT offset_bytes, first_ts, last_origin FROM ingest_state WHERE source_path=?", (rel,)).fetchone()
    offset = row[0] if row else 0
    if row and st.st_size == offset:
        stats["files_unchanged"] += 1
        return
    if row and st.st_size < offset:
        offset = 0
        stats["files_reset"] += 1
    lines, new_off = read_new_lines(path, offset)
    key = owner_key(root, path)
    first_ts = row[1] if (row and offset > 0) else first_timestamp(lines)
    if first_ts is None and row:
        first_ts = row[1]
    best, number, synthetic, bad, last_origin = parse_lines(lines, row[2] if (row and offset > 0) else None)
    stats["synthetic"] += synthetic
    stats["bad_lines"] += bad
    stats["lines_read"] += len(lines)
    with con:
        con.execute(
            "INSERT INTO ingest_state(source_path, offset_bytes, size_bytes, mtime, updated_at, first_ts, session_key, last_origin) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(source_path) DO UPDATE SET offset_bytes=excluded.offset_bytes, "
            "size_bytes=excluded.size_bytes, mtime=excluded.mtime, updated_at=excluded.updated_at, "
            "first_ts=excluded.first_ts, session_key=excluded.session_key, last_origin=excluded.last_origin",
            (rel, new_off, st.st_size, st.st_mtime, usage_db.now_iso(), first_ts, key, last_origin))
        if best:
            upsert_turns(con, rel, key, first_ts, best, stats)
        if number:
            con.execute("INSERT OR IGNORE INTO sessions(session_key) VALUES (?)", (key,))
            con.execute("UPDATE sessions SET number=?, number_source='custom-title' WHERE session_key=?", (number, key))
    stats["files_ingested"] += 1


def upsert_turns(con, rel, key, first_ts, best, stats):
    ts_all = [r["ts"] for r in best.values()]
    cwd = branch = None
    for r in sorted(best.values(), key=lambda r: r["ts"]):
        cwd = r["cwd"] or cwd
        branch = r["branch"] or branch
    con.execute("INSERT OR IGNORE INTO sessions(session_key) VALUES (?)", (key,))
    con.execute(
        "UPDATE sessions SET first_seen = CASE WHEN first_seen IS NULL OR first_seen > ? THEN ? ELSE first_seen END, "
        "last_seen = CASE WHEN last_seen IS NULL OR last_seen < ? THEN ? ELSE last_seen END, "
        "cwd = COALESCE(?, cwd), branch = COALESCE(?, branch) WHERE session_key=?",
        (min(ts_all), min(ts_all), max(ts_all), max(ts_all), cwd, branch, key))
    ids = list(best)
    existing = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        q = ("SELECT t.message_id, t.source_path, t.output_tokens, COALESCE(s.first_ts, ''), t.session_key, t.turn_origin, t.sid_rank FROM usage_turns t "
             "LEFT JOIN ingest_state s ON s.source_path = t.source_path WHERE t.message_id IN (%s)" % ",".join("?" * len(chunk)))
        for mid, src, out, fts, skey, org, rk in con.execute(q, chunk):
            existing[mid] = (src, out, fts, skey, org, rk)
    for mid, r in best.items():
        ex = existing.get(mid)
        rank = 0 if key == r["sid"] else 1
        vals = (key, r["ts"], r["model"], r["inp"], r["cc"], r["cr"], r["out"], r["think"], r["side"], r["req"], rel, r["origin"], rank,
                r["cc1h"], r["cc5m"], mid)
        if ex is None:
            con.execute("INSERT INTO usage_turns(session_key, ts, model, input_tokens, cache_creation_tokens, "
                        "cache_read_tokens, output_tokens, thinking_tokens, is_sidechain, request_id, source_path, "
                        "turn_origin, sid_rank, cc_1h, cc_5m, message_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", vals)
            stats["turns_new"] += 1
        elif ex[0] == rel:
            if r["out"] > ex[1] or (ex[4] is None and r["origin"]) or ex[5] is None:
                con.execute("UPDATE usage_turns SET output_tokens=MAX(output_tokens, ?), thinking_tokens=?, ts=?, "
                            "turn_origin=COALESCE(?, turn_origin), sid_rank=?, cc_1h=COALESCE(?, cc_1h), cc_5m=COALESCE(?, cc_5m) "
                            "WHERE message_id=?", (r["out"], r["think"], r["ts"], r["origin"], rank, r["cc1h"], r["cc5m"], mid))
                stats["turns_updated"] += 1
        elif (rank, first_ts or "", rel) < (1 if ex[5] is None else ex[5], ex[2], ex[0]):
            con.execute("UPDATE usage_turns SET session_key=?, ts=?, model=?, input_tokens=?, cache_creation_tokens=?, "
                        "cache_read_tokens=?, output_tokens=MAX(output_tokens, ?), thinking_tokens=?, is_sidechain=?, "
                        "request_id=?, source_path=?, turn_origin=?, sid_rank=?, cc_1h=?, cc_5m=? WHERE message_id=?",
                        (key, r["ts"], r["model"], r["inp"], r["cc"], r["cr"], r["out"], r["think"], r["side"],
                         r["req"], rel, r["origin"], rank, r["cc1h"], r["cc5m"], mid))
            stats["turns_reassigned"] += 1
        else:
            stats["turns_dup_skipped"] += 1


def apply_app_numbers(con, app_dir, stats):
    """احتياط: رقم من عنوان ملف التطبيق لجلسة بلا رقم. يُقرأ cliSessionId وpriorCliSessionIds والعنوان فقط، ويُحفظ الرقم وحده."""
    n = 0
    for fp in glob.glob(os.path.join(app_dir, "*", "*", "local_*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        m = NUM_RE.match(str(d.get("title") or ""))
        if not m:
            continue
        ids = [d.get("cliSessionId")] + list(d.get("priorCliSessionIds") or [])
        for sid in filter(None, ids):
            cur = con.execute("UPDATE sessions SET number=?, number_source='app' WHERE session_key=? AND number IS NULL",
                              (m.group(1), sid))
            n += cur.rowcount
    con.commit()
    stats["numbers_from_app"] = n


def run(con, root=PROJECTS, app_dir=APP_SESSIONS):
    stats = dict(files_ingested=0, files_unchanged=0, files_reset=0, files_error=0, lines_read=0, synthetic=0,
                 bad_lines=0, turns_new=0, turns_updated=0, turns_reassigned=0, turns_dup_skipped=0)
    for path in sorted(iter_logs(root)):
        try:
            ingest_file(con, root, path, stats)
        except OSError:
            stats["files_error"] += 1
    if app_dir and os.path.isdir(app_dir):
        apply_app_numbers(con, app_dir, stats)
    with con:  # بعد إعادة الإسناد: مدى الجلسة من ردودها الفعلية
        con.execute("UPDATE sessions SET first_seen=(SELECT MIN(ts) FROM usage_turns t WHERE t.session_key=sessions.session_key), "
                    "last_seen=(SELECT MAX(ts) FROM usage_turns t WHERE t.session_key=sessions.session_key) "
                    "WHERE EXISTS (SELECT 1 FROM usage_turns t WHERE t.session_key=sessions.session_key)")
    stats["turns_total"] = con.execute("SELECT COUNT(*) FROM usage_turns").fetchone()[0]
    stats["sessions_total"] = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=None)
    ap.add_argument("--root", default=PROJECTS)
    ap.add_argument("--app-dir", default=APP_SESSIONS)
    a = ap.parse_args(argv)
    t = time.time()
    con = usage_db.connect(a.db)
    stats = run(con, a.root, a.app_dir)
    stats["seconds"] = round(time.time() - t, 1)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
