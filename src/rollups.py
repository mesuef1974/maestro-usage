"""تجميعات الاستهلاك: usage_rollups (يوم/أسبوع/شهر × نموذج) وملخّص الجلسة. أرقام فقط، ولا رقم خارج usage_turns.

الأسبوع يبدأ الاثنين بالتوقيت العالمي. إعادة التحديث كاملة في معاملة واحدة فلا يرى قارئٌ جدولًا نصف مكتوب، وتكرارها لا يغيّر الأرقام.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_db  # noqa: E402

# تعبير بداية الفترة لكل مستوى (SQLite)؛ ts نصّ ISO فأول 10 أحرف اليوم.
_START = {
    "day": "substr(ts, 1, 10)",
    "week": "date(substr(ts, 1, 10), '-6 days', 'weekday 1')",
    "month": "substr(ts, 1, 7) || '-01'",
}
_COLS = ("input_tokens", "cache_creation_tokens", "cache_read_tokens", "output_tokens")


def refresh(con):
    """يعيد بناء usage_rollups من usage_turns؛ يعيد عدد الصفوف."""
    now = usage_db.now_iso()
    with con:  # معاملة واحدة
        con.execute("DELETE FROM usage_rollups")
        for grain, expr in _START.items():
            con.execute(
                "INSERT INTO usage_rollups(grain, period_start, model, turns, sessions, input_tokens, cache_creation_tokens, "
                "cache_read_tokens, output_tokens, thinking_tokens, refreshed_at) "
                "SELECT ?, %s AS p, model, COUNT(*), COUNT(DISTINCT session_key), SUM(input_tokens), SUM(cache_creation_tokens), "
                "SUM(cache_read_tokens), SUM(output_tokens), SUM(thinking_tokens), ? FROM usage_turns GROUP BY p, model" % expr,
                (grain, now))
    return con.execute("SELECT COUNT(*) FROM usage_rollups").fetchone()[0]


def _row(r):
    return dict(zip(("period", "turns", "input", "cache_creation", "cache_read", "output"), r))


def periods(con, grain, n):
    """آخر n فترة (الأحدث أولًا) مجموعةً على كل النماذج، مع الجلسات المميّزة."""
    rows = con.execute(
        "SELECT period_start, SUM(turns), SUM(input_tokens), SUM(cache_creation_tokens), SUM(cache_read_tokens), SUM(output_tokens) "
        "FROM usage_rollups WHERE grain = ? GROUP BY period_start ORDER BY period_start DESC LIMIT ?", (grain, n)).fetchall()
    out = []
    for r in rows:
        d = _row(r)
        d["sessions"] = con.execute(
            "SELECT COUNT(DISTINCT session_key) FROM usage_turns WHERE ts >= ? AND ts < ?", (r[0], _next(con, grain, r[0]))).fetchone()[0]
        out.append(d)
    return out


def _next(con, grain, start):
    """بداية الفترة التالية (حدّ أعلى حصري)."""
    step = {"day": "+1 day", "week": "+7 days", "month": "+1 month"}[grain]
    return con.execute("SELECT date(?, ?)", (start, step)).fetchone()[0]


def models(con, grain, start):
    """نماذج فترة واحدة، الأكثر أدوارًا أولًا."""
    return [dict(model=r[0], turns=r[1], input=r[2], cache_creation=r[3], cache_read=r[4], output=r[5]) for r in con.execute(
        "SELECT model, turns, input_tokens, cache_creation_tokens, cache_read_tokens, output_tokens FROM usage_rollups "
        "WHERE grain = ? AND period_start = ? ORDER BY turns DESC", (grain, start))]


def last_session(con):
    """أحدث جلسة نشاطًا: إجماليها ونماذجها."""
    r = con.execute("SELECT session_key, first_ts, last_ts, turns, input_tokens, cache_creation_tokens, cache_read_tokens, output_tokens "
                    "FROM v_session_totals ORDER BY last_ts DESC LIMIT 1").fetchone()
    if not r:
        return None
    ms = [dict(model=m[0], turns=m[1], input=m[2], cache_creation=m[3], cache_read=m[4], output=m[5]) for m in con.execute(
        "SELECT model, COUNT(*), SUM(input_tokens), SUM(cache_creation_tokens), SUM(cache_read_tokens), SUM(output_tokens) "
        "FROM usage_turns WHERE session_key = ? GROUP BY model ORDER BY 2 DESC", (r[0],))]
    return dict(key=r[0], first=r[1], last=r[2], turns=r[3], input=r[4], cache_creation=r[5], cache_read=r[6], output=r[7], models=ms)


def payload(con):
    refresh(con)
    start_w, start_m = (con.execute("SELECT MAX(period_start) FROM usage_rollups WHERE grain = ?", (g,)).fetchone()[0] for g in ("week", "month"))
    return dict(session=last_session(con), weekly=periods(con, "week", 8), monthly=periods(con, "month", 6),
                week_models=models(con, "week", start_w) if start_w else [], month_models=models(con, "month", start_m) if start_m else [],
                week_start=start_w, month_start=start_m)
