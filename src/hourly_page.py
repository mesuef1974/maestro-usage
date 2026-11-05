"""قسم «التوكنات بالساعة»: توكنات كل ساعة (UTC) مجموعةً على كل النماذج، منحنى تراكمي أو لكل ساعة.

الحمولة: h = صفوف [ساعة بالعدّ منذ 1970، توكنات الساعة] (إدخال + كتابة ذاكرة + قراءة ذاكرة + مخرجات، كل الردود).
لقطات الحصة plan_rows تخدم أيضًا نقطة /plan.json الحيّة في الخادم.
"""
from datetime import datetime


def _epoch(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def payload(con):
    hours = {}
    for ts, i, cc, cr, u in con.execute("SELECT ts, input_tokens, cache_creation_tokens, cache_read_tokens, output_tokens FROM usage_turns ORDER BY ts"):
        h = int(_epoch(ts) // 3600)
        hours[h] = hours.get(h, 0) + i + cc + cr + u
    return dict(h=[[h, v] for h, v in sorted(hours.items())])


DENSE_HOURS = 48  # آخر يومين بكل لقطة (كل 5 دقائق)؛ الأقدم لقطة واحدة في الساعة، فلا تتضخم الصفحة مع الأيام


def thin_plan(rows, now_ts, dense_hours=DENSE_HOURS):
    """يرقّق اللقطات القديمة: ما قبل dense_hours تبقى أول لقطة من كل ساعة، مع آخر لقطة وآخر لقطة تحمل Fable دائمًا."""
    if not rows:
        return rows
    from datetime import timedelta
    cut = (datetime.strptime(now_ts[:19], "%Y-%m-%dT%H:%M:%S") - timedelta(hours=dense_hours)).strftime("%Y-%m-%dT%H:%M:%S")
    keep, seen = [], set()
    last_fa = max((r for r in rows if r["fa"] is not None), key=lambda r: r["ts"], default=None)
    for r in rows:
        if r["ts"] >= cut or r is rows[-1] or r is last_fa:
            keep.append(r)
            continue
        h = r["ts"][:13]
        if h not in seen:
            seen.add(h)
            keep.append(r)
    return keep


def plan_rows(con, thin=True):
    """لقطات الحصة بالشكل الذي تقرؤه الصفحة (D.plan)؛ يخدم البناء الثابت ونقطة /plan.json الحيّة. thin يرقّق القديم."""
    rows = [dict(ts=ts, f=f, fr=fr, w=w, wr=wr, fa=fa, far=far, pl=pl, src=src) for ts, f, fr, w, wr, fa, far, pl, src in con.execute(
        "SELECT ts, five_hour_pct, five_hour_resets_at, seven_day_pct, seven_day_resets_at, fable_pct, fable_resets_at, plan, source "
        "FROM plan_snapshots ORDER BY ts")]
    return thin_plan(rows, rows[-1]["ts"]) if thin and rows else rows
