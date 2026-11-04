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


def plan_rows(con):
    """لقطات الحصة بالشكل الذي تقرؤه الصفحة (D.plan)؛ يخدم البناء الثابت ونقطة /plan.json الحيّة."""
    return [dict(ts=ts, f=f, fr=fr, w=w, wr=wr, fa=fa, far=far, pl=pl, src=src) for ts, f, fr, w, wr, fa, far, pl, src in con.execute(
        "SELECT ts, five_hour_pct, five_hour_resets_at, seven_day_pct, seven_day_resets_at, fable_pct, fable_resets_at, plan, source "
        "FROM plan_snapshots ORDER BY ts")]
