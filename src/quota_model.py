"""كلفة الحصة: كم توكنًا مقاسًا يقابل 1% من الحصة الأسبوعية، ومعدل الحرق، والمتوقَّع عند التصفير. أرقام فقط من plan_snapshots وusage_turns.

المنهج: النسبة في اللقطات عدد صحيح مقرَّب، فلا يُعرف منها إلا لحظات الانتقال (أول لقطة تحمل قيمة أعلى من سابقتها). الانتقال «دقيق»
إن سبقته لقطة قبل أقل من PRECISE_GAP ثانية، فزمن الصعود معروف ضمن تلك الفجوة؛ والفجوات الطويلة (نوم الحاسوب أو توقّف الجامع) تُسقط
الانتقال. تُجمع التوكنات المقاسة بين كل انتقالين دقيقين متتاليين صاعدين، والتقدير = مجموع التوكنات ÷ مجموع فروق النسبة (مرجّح بالحجم)،
ومعه الوسيط والمدى وعدد الأزواج. لا تقدير إن قلّت الأزواج عن MIN_PAIRS. الدقة محدودة بتقريب النسبة إلى 1%، فالمدى واسع في الأسابيع الأولى.
الترجيح بأسعار الأنواع (قراءة الذاكرة أرخص من المخرجات) لم يثبت على البيانات الحالية أنه يفسّر الحصة أفضل من الخام، فالمقياس هنا الخام.
حدّ الخطة: إن اختفت نافذة الخمس ساعات من اللقطات (الانتقال إلى خطة Ultra في 2026-10-31) فالأزواج قبل آخر لقطة حملتها تُسقط، لأن كلفة 1%
في الخطة السابقة مختلفة (85 مليونًا مقابل 23 مليونًا بعدها) وخلطهما يضلّل.
التوقّع: معدل الحرق «مرصود» = فرق النسبة بين آخر لقطة ولقطة قبل BURN_HOURS ساعة أو أكثر ÷ الساعات بينهما (من اللقطات مباشرة، لا يحتاج
كلفة التوكن)، وإن لم تتوفر لقطة قديمة كافية (MIN_OBS_HOURS) أو حدث تصفير بينهما فالاحتياط «مشتق من التوكنات» = توكنات آخر BURN_HOURS ساعة ÷
كلفة 1% ÷ الساعات. المتوقَّع عند التصفير = آخر نسبة + المعدل × الساعات المتبقية، وإن تجاوز 100 فيُحسب وقت بلوغ 100 بالمعدل نفسه.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from statistics import median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_db  # noqa: E402

PRECISE_GAP = 11 * 60  # ثانية: أقصى فجوة قبل الانتقال كي يُعدّ زمنه معروفًا (الجامع كل 5 دقائق، مع سماحة)
MIN_PAIRS = 3
BURN_HOURS = 24
MIN_OBS_HOURS = 6  # أقل مدة بين لقطتين ليُعدّ معدل الحرق المرصود منهما صالحًا
WINDOWS = {  # اسم → (عمود النسبة، عمود التصفير، مرشّح النموذج في usage_turns أو None)
    "week": ("seven_day_pct", "seven_day_resets_at", None),
    "fable": ("fable_pct", "fable_resets_at", "claude-fable-%"),
}


def _epoch(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def _tokens(con, a, b, model_like=None):
    sql = "SELECT COALESCE(SUM(input_tokens+cache_creation_tokens+cache_read_tokens+output_tokens),0) FROM usage_turns WHERE ts>=? AND ts<?"
    args = [a, b]
    if model_like:
        sql += " AND model LIKE ?"
        args.append(model_like)
    return con.execute(sql, args).fetchone()[0]


def transitions(con, pct_col):
    """لحظات تغيّر النسبة: (زمن اللقطة السابقة، زمن أول لقطة بالقيمة الجديدة، النسبة قبل، النسبة بعد، دقيق؟)."""
    out, prev = [], None
    for ts, pct in con.execute("SELECT ts, %s FROM plan_snapshots WHERE %s IS NOT NULL ORDER BY ts" % (pct_col, pct_col)):
        if prev is not None and pct != prev[1]:
            out.append((prev[0], ts, prev[1], pct, _epoch(ts) - _epoch(prev[0]) <= PRECISE_GAP))
        prev = (ts, pct)
    return out


def plan_since(con):
    """بداية الخطة الحالية: زمن آخر لقطة حملت نافذة الخمس ساعات إن كانت قد اختفت من اللقطات اللاحقة (تغيّر الخطة)، وإلا None."""
    last = con.execute("SELECT ts, five_hour_pct FROM plan_snapshots WHERE seven_day_pct IS NOT NULL ORDER BY ts DESC LIMIT 1").fetchone()
    last5 = con.execute("SELECT MAX(ts) FROM plan_snapshots WHERE five_hour_pct IS NOT NULL").fetchone()[0]
    if last and last5 and last[1] is None and last5 < last[0]:
        return last5
    return None


def pairs(con, pct_col, model_like=None):
    """أزواج انتقالين دقيقين متتاليين صاعدين بعد حدّ الخطة الحالية: (من، إلى، فرق النسبة، التوكنات المقاسة بينهما)."""
    tr = transitions(con, pct_col)
    since = plan_since(con)
    out = []
    for k in range(1, len(tr)):
        a, b = tr[k - 1], tr[k]
        d = b[3] - a[3]
        if since and a[0] < since:
            continue  # زوج يبدأ قبل تغيّر الخطة: كلفته من خطة أخرى
        if a[4] and b[4] and d > 0 and b[3] > b[2]:
            out.append((a[1], b[1], d, _tokens(con, a[1], b[1], model_like)))
    return out


def cost(con, pct_col, model_like=None):
    """توكن لكل 1%: التقدير المرجّح والوسيط والمدى وعدد الأزواج، أو None إن قلّت الأزواج."""
    ps = pairs(con, pct_col, model_like)
    if len(ps) < MIN_PAIRS:
        return dict(since=plan_since(con), n=len(ps), per_pct=None)
    per = sorted(t / d for _a, _b, d, t in ps)
    return dict(since=plan_since(con), n=len(ps), per_pct=sum(t for *_x, t in ps) / sum(d for _a, _b, d, _t in ps), med=median(per), lo=per[0], hi=per[-1],
                span_from=ps[0][0], span_to=ps[-1][1])


def forecast(con, pct_col, resets_col, per_pct, model_like=None, now=None):
    """آخر نسبة وزمن تصفيرها، ومعدل الحرق (مرصود من اللقطات، وإلا مشتق من توكنات آخر 24 ساعة ÷ كلفة 1%)، والمتوقَّع عند التصفير أو وقت بلوغ 100."""
    row = con.execute("SELECT ts, %s, %s FROM plan_snapshots WHERE %s IS NOT NULL ORDER BY ts DESC LIMIT 1" % (pct_col, resets_col, pct_col)).fetchone()
    if not row:
        return None
    ts, pct, resets = row
    out = dict(ts=ts, pct=pct, resets=resets, rate_day=None, rate_src=None, obs_from=None, at_reset=None, full_at=None)
    now = now or datetime.now(timezone.utc)
    rate_h = None
    old = con.execute("SELECT ts, %s FROM plan_snapshots WHERE %s IS NOT NULL AND ts <= ? ORDER BY ts DESC LIMIT 1" % (pct_col, pct_col),
                      ((now - timedelta(hours=BURN_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ"),)).fetchone()
    boundary = plan_since(con)
    if old and old[1] <= pct and (boundary is None or old[0] >= boundary) and (not resets or _epoch(old[0]) >= _epoch(resets) - 7 * 86400):
        hours = (_epoch(ts) - _epoch(old[0])) / 3600  # بين اللقطتين نفسيهما لا حتى الآن: ما بعد آخر لقطة غير مقيس
        if hours >= MIN_OBS_HOURS:
            rate_h, out["rate_src"], out["obs_from"] = (pct - old[1]) / hours, "observed", old[0]
    if rate_h is None:
        if per_pct is None:
            return out
        since = (now - timedelta(hours=BURN_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        tok = _tokens(con, since, now.strftime("%Y-%m-%dT%H:%M:%SZ"), model_like)
        rate_h, out["rate_src"] = tok / per_pct / BURN_HOURS, "tokens"
    out["rate_day"] = rate_h * 24
    if resets:
        hours_left = max(0.0, (_epoch(resets) - now.timestamp()) / 3600)
        proj = pct + rate_h * hours_left
        out["at_reset"] = proj
        if proj > 100 and rate_h > 0:
            out["full_at"] = (now + timedelta(hours=(100 - pct) / rate_h)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def payload(con, now=None):
    """لكل نافذة: cost وforecast؛ تُضمَّن في حمولة اللوحة تحت المفتاح quota."""
    out = {}
    for name, (pct_col, resets_col, model_like) in WINDOWS.items():
        c = cost(con, pct_col, model_like)
        out[name] = dict(cost=c, fc=forecast(con, pct_col, resets_col, c.get("per_pct"), model_like, now))
    return out


if __name__ == "__main__":
    import json
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(payload(usage_db.connect()), ensure_ascii=False, indent=1))
