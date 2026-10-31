"""جدول يومي لدراسة أثر الإعدادات على الاستهلاك (قبل/بعد) بمقاييس لا يحجبها سقف الضغط: قراءة الذاكرة لكل ردّ ولكل جلسة فعّالة.

كل صف يوم UTC. «مستوى الضغط» = وسيط سياق الردّ السابق عند هبوط السياق (تقدير الضغط التلقائي، ≥ 100 ألف): يكشف السقف الفعلي لليوم
بلا حاجة لقراءة الإعدادات (أكتوبر 2026: ≈293 ألفًا مع override=30، ≈147 ألفًا مع 15، ≈1 مليون بلا override).
متغيّرات ضابطة للبند 6: عدد الجلسات والأدوار الفعّالة، وردود الإنسان، وحصة peer.
التشغيل: python src\\study.py [--from 2026-10-08] ؛ يكتب reports\\study_daily.csv وreports\\study_wake_by_msgs.csv ويطبع الجدول.

أعمدة الإنجاز (inbox #15): «الإنجاز» صنفان منفصلان لا يُجمعان: إيداعات git (مستودعا shschool_mvp وdelivery_manager_work، كل الفروع،
بلا دمج، بتاريخ المُودِع UTC) وبطاقات الدفتر (أول انتقال للبطاقة إلى merged أو published أو closed). ومقاييسهما: cr_per_commit وcr_per_card.
البند 2: تكلفة الإيقاظ (cc عند الردّ بعد فجوة > ساعة) مقابل رسائل صندوق الدور بين الردّين (study_wake_by_msgs.csv).
البند 6: عمود event يحمل علامات تغيّر الإعدادات وتصفير عدّاد الرسائل.
"""
import argparse
import csv
import json
import os
import subprocess
import sys
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402
import reports  # noqa: E402
import role_groups  # noqa: E402
import sessions_page  # noqa: E402
import usage_db  # noqa: E402

COLS = ["day", "replies", "main", "cr", "cc", "u", "cr_per_reply", "sessions", "cr_per_session", "roles", "human", "peer_pct",
        "wake", "wake_cc", "drops", "level_med", "p99_ctx", "max_ctx"]


EXTRA_COLS = ["commits_shschool", "commits_dmw", "cards_done", "cr_per_commit", "cr_per_card", "msgs", "wake_msgs",
              "event"]
DMW = "C:/Users/mesue/delivery_manager_work"
SHSCHOOL = "D:/shschool_mvp"
DONE_STATES = ("merged", "published", "closed")
BUCKETS = [("0", 0, 0), ("1", 1, 1), ("2-3", 2, 3), ("4+", 4, 10 ** 9)]
DOHA = timezone(timedelta(hours=3))


def _epoch(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def _utc_day(ts):
    return datetime.fromtimestamp(_epoch(ts), timezone.utc).strftime("%Y-%m-%d")


def daily(con, first=None):
    number = {k: n for k, n in con.execute("SELECT session_key, number FROM sessions") if n and role_groups.is_project(n)}
    d = defaultdict(lambda: dict(replies=0, main=0, cr=0, cc=0, u=0, sess=set(), roles=set(), human=0, peer=0,
                                 wake=0, wake_cc=0, drops=[], ctx=[]))
    prev = {}
    cur = con.execute(
        "SELECT session_key, ts, input_tokens, cache_creation_tokens, cache_read_tokens, output_tokens, is_sidechain, turn_origin "
        "FROM usage_turns ORDER BY session_key, ts, message_id")
    for key, ts, i, cc, cr, u, side, org in cur:
        day = ts[:10]
        x = d[day]
        x["replies"] += 1
        x["cr"] += cr
        x["cc"] += cc
        x["u"] += u
        x["sess"].add(key)
        if key in number:
            x["roles"].add(number[key])
        if side:
            continue
        ctx = i + cc + cr
        x["main"] += 1
        x["ctx"].append(ctx)
        o = dashboard._origin(org)
        x["human"] += o == "human"
        x["peer"] += o == "peer"
        p = prev.get(key)
        e = _epoch(ts)
        if p:
            if e - p[0] > sessions_page.WAKE_GAP_SEC:
                x["wake"] += 1
                x["wake_cc"] += cc
            if p[1] >= sessions_page.DROP_MIN_PREV and ctx < sessions_page.DROP_RATIO * p[1]:
                x["drops"].append(p[1])
        prev[key] = (e, ctx)
    rows = []
    for day in sorted(d):
        if first and day < first:
            continue
        x = d[day]
        cs = sorted(x["ctx"])
        rows.append(dict(
            day=day, replies=x["replies"], main=x["main"], cr=x["cr"], cc=x["cc"], u=x["u"],
            cr_per_reply=round(x["cr"] / x["replies"]) if x["replies"] else 0,
            sessions=len(x["sess"]), cr_per_session=round(x["cr"] / len(x["sess"])) if x["sess"] else 0,
            roles=len(x["roles"]), human=x["human"], peer_pct=round(100 * x["peer"] / x["main"], 1) if x["main"] else 0,
            wake=x["wake"], wake_cc=x["wake_cc"], drops=len(x["drops"]),
            level_med=round(median(x["drops"])) if x["drops"] else "", p99_ctx=cs[int(len(cs) * .99)] if cs else 0,
            max_ctx=cs[-1] if cs else 0))
    return rows


def git_commits(path):
    """{يوم UTC: عدد} للإيداعات المميّزة في كل الفروع بلا دمج؛ {} إن تعذّر قراءة المستودع."""
    try:
        out = subprocess.run(["git", "-C", path, "log", "--branches", "--remotes", "--no-merges", "--format=%H %cI"],
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return {}
    days = {}
    for line in out.splitlines():
        h, _, ts = line.partition(" ")
        if h and ts:
            days[h] = _utc_day(ts)
    n = defaultdict(int)
    for day in days.values():
        n[day] += 1
    return dict(n)


def ledger_done(path):
    """{يوم UTC: عدد البطاقات} التي بلغت merged أو published أو closed لأول مرة في ذلك اليوم."""
    first = {}
    try:
        f = open(path, encoding="utf-8")
    except OSError:
        return {}
    with f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("kind") != "state" or (e.get("data") or {}).get("state") not in DONE_STATES:
                continue
            if e["id"] not in first or _epoch(e["ts"]) < _epoch(first[e["id"]]):
                first[e["id"]] = e["ts"]
    n = defaultdict(int)
    for ts in first.values():
        n[_utc_day(ts)] += 1
    return dict(n)


def inbox_times(directory):
    """{دور: أزمنة وصول رسائله (epoch) مرتّبة} من ملفات <الدور>.jsonl (سجلات k=msg)."""
    out = {}
    try:
        names = os.listdir(directory)
    except OSError:
        return out
    for name in names:
        if not name.endswith(".jsonl") or not role_groups.is_project(name[:-6]):
            continue
        ts = []
        with open(os.path.join(directory, name), encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("k") == "msg":
                    ts.append(_epoch(e["ts"]))
        out[name[:-6]] = sorted(ts)
    return out


def wake_events(con, inbox):
    """إيقاظات الأدوار ذات الصندوق: لكل إيقاظ عدد الرسائل الواصلة بين الردّ السابق والإيقاظ وكلفته cc وcr."""
    number = {k: n for k, n in con.execute("SELECT session_key, number FROM sessions") if n and n in inbox}
    prev = {}
    out = []
    for key, ts, cc, cr in con.execute(
            "SELECT session_key, ts, cache_creation_tokens, cache_read_tokens FROM usage_turns "
            "WHERE is_sidechain=0 ORDER BY session_key, ts, message_id"):
        e = _epoch(ts)
        p = prev.get(key)
        prev[key] = e
        if p is None or e - p <= sessions_page.WAKE_GAP_SEC or key not in number:
            continue
        t = inbox[number[key]]
        out.append(dict(day=ts[:10], role=number[key], cc=cc, cr=cr, msgs=bisect_right(t, e) - bisect_right(t, p)))
    return out


def wake_by_msgs(events, first_day):
    rows = []
    for label, lo, hi in BUCKETS:
        xs = [w for w in events if w["day"] >= first_day and lo <= w["msgs"] <= hi]
        rows.append(dict(bucket=label, wakes=len(xs), cc_mean=round(mean(w["cc"] for w in xs)) if xs else "",
                         cc_median=round(median(w["cc"] for w in xs)) if xs else "",
                         cr_mean=round(mean(w["cr"] for w in xs)) if xs else ""))
    return rows


def events(con, counter_path):
    """{يوم: نص} علامات تغيّر الإعدادات (config_changes) وتصفير عدّاد الرسائل (since بعد بدء العدّ) بتاريخ UTC."""
    ev = defaultdict(list)
    for ts, key, old, new in con.execute("SELECT ts, key, old_value, new_value FROM config_changes ORDER BY ts, id"):
        ev[ts[:10]].append(f"{key}: {old}→{new}")
    try:
        with open(counter_path, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    for role, v in (c.get("sessions") or {}).items():
        since = v.get("since")
        if since and since != c.get("started"):
            utc = datetime.strptime(since, "%Y-%m-%d %H:%M").replace(tzinfo=DOHA).astimezone(timezone.utc)
            ev[utc.strftime("%Y-%m-%d")].append(f"تصفير عدّاد {role} {utc.strftime('%H:%M')}Z")
    return {d: " | ".join(v) for d, v in ev.items()}


def enrich(rows, commits, cards, inbox, wakes, ev):
    msgs = defaultdict(int)
    for t in (t for v in inbox.values() for t in v):
        msgs[datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")] += 1
    wake_msgs = defaultdict(int)
    for w in wakes:
        wake_msgs[w["day"]] += w["msgs"]
    for r in rows:
        d = r["day"]
        c1, c2 = commits.get("shschool", {}).get(d, 0), commits.get("dmw", {}).get(d, 0)
        k = cards.get(d, 0)
        r.update(commits_shschool=c1, commits_dmw=c2, cards_done=k,
                 cr_per_commit=round(r["cr"] / (c1 + c2)) if c1 + c2 else "", cr_per_card=round(r["cr"] / k) if k else "",
                 msgs=msgs.get(d, 0), wake_msgs=wake_msgs.get(d, 0), event=ev.get(d, ""))
    return rows


def _write(path, cols, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="first", default=None)
    ap.add_argument("--db")
    ap.add_argument("--shschool", default=SHSCHOOL)
    ap.add_argument("--dmw", default=DMW)
    a = ap.parse_args(argv)
    con = usage_db.connect(a.db)
    inbox = inbox_times(os.path.join(a.dmw, "ledger", "inbox"))
    wakes = wake_events(con, inbox)
    rows = enrich(daily(con, a.first), {"shschool": git_commits(a.shschool), "dmw": git_commits(a.dmw)},
                  ledger_done(os.path.join(a.dmw, "ledger", "events.jsonl")), inbox, wakes,
                  events(con, os.path.join(a.dmw, "msg_counter.json")))
    os.makedirs(reports.REPORTS_DIR, exist_ok=True)
    cols = COLS + EXTRA_COLS
    path = os.path.join(reports.REPORTS_DIR, "study_daily.csv")
    _write(path, cols, rows)
    first_inbox = min((datetime.fromtimestamp(t[0], timezone.utc).strftime("%Y-%m-%d") for t in inbox.values() if t), default="")
    bcols = ["bucket", "wakes", "cc_mean", "cc_median", "cr_mean"]
    buckets = wake_by_msgs(wakes, first_inbox)
    _write(os.path.join(reports.REPORTS_DIR, "study_wake_by_msgs.csv"), bcols, buckets)
    print("\t".join(cols))
    for r in rows:
        print("\t".join(str(r[c]) for c in cols))
    print(f"\nإيقاظ حسب عدد الرسائل (منذ {first_inbox}):")
    for b in buckets:
        print("\t".join(str(b[c]) for c in bcols))
    print(path)


if __name__ == "__main__":
    main()
