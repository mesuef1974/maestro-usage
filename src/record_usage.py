"""يسجّل لقطة حصة الخطة في plan_snapshots بمصدر get_usage (تُقرأ الأرقام من أداة get_usage داخل جلسة، لا من السجلات).

مثال: python record_usage.py --five 2 --five-resets 2026-10-29T14:49:59Z --seven 4 --seven-resets 2026-11-04T16:59:59Z --plan Max
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_db  # noqa: E402


def record(con, five, five_resets, seven, seven_resets, plan=None, ts=None):
    ts = ts or usage_db.now_iso()
    cur = con.execute(
        "INSERT OR IGNORE INTO plan_snapshots(ts, session_key, five_hour_pct, five_hour_resets_at, seven_day_pct, "
        "seven_day_resets_at, source, plan) VALUES (?,NULL,?,?,?,?, 'get_usage', ?)",
        (ts, five, five_resets, seven, seven_resets, plan))
    con.commit()
    return cur.rowcount


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--five", type=float)
    ap.add_argument("--five-resets")
    ap.add_argument("--seven", type=float)
    ap.add_argument("--seven-resets")
    ap.add_argument("--plan")
    ap.add_argument("--db")
    a = ap.parse_args(argv)
    if a.five is None and a.seven is None:
        ap.error("يلزم --five أو --seven")
    n = record(usage_db.connect(a.db), a.five, a.five_resets, a.seven, a.seven_resets, a.plan)
    print("recorded" if n else "duplicate")


if __name__ == "__main__":
    main()
