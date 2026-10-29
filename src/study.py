"""جدول يومي لدراسة أثر الإعدادات على الاستهلاك (قبل/بعد) بمقاييس لا يحجبها سقف الضغط: قراءة الذاكرة لكل ردّ ولكل جلسة فعّالة.

كل صف يوم UTC. «مستوى الضغط» = وسيط سياق الردّ السابق عند هبوط السياق (تقدير الضغط التلقائي، ≥ 100 ألف): يكشف السقف الفعلي لليوم
بلا حاجة لقراءة الإعدادات (أكتوبر 2026: ≈293 ألفًا مع override=30، ≈147 ألفًا مع 15، ≈1 مليون بلا override).
متغيّرات ضابطة للبند 6: عدد الجلسات والأدوار الفعّالة، وردود الإنسان، وحصة peer.
التشغيل: python src\\study.py [--from 2026-10-08] ؛ يكتب reports\\study_daily.csv ويطبع الجدول.
"""
import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime
from statistics import median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402
import reports  # noqa: E402
import role_groups  # noqa: E402
import sessions_page  # noqa: E402
import usage_db  # noqa: E402

COLS = ["day", "replies", "main", "cr", "cc", "u", "cr_per_reply", "sessions", "cr_per_session", "roles", "human", "peer_pct",
        "wake", "wake_cc", "drops", "level_med", "p99_ctx", "max_ctx"]


def _epoch(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="first", default=None)
    ap.add_argument("--db")
    a = ap.parse_args(argv)
    rows = daily(usage_db.connect(a.db), a.first)
    os.makedirs(reports.REPORTS_DIR, exist_ok=True)
    path = os.path.join(reports.REPORTS_DIR, "study_daily.csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(rows)
    print("\t".join(COLS))
    for r in rows:
        print("\t".join(str(r[c]) for c in COLS))
    print(path)


if __name__ == "__main__":
    main()
