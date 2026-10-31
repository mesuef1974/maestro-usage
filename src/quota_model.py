"""كلفة الحصة: كم توكنًا مقاسًا يقابل 1% من الحصة الأسبوعية، ومعدل الحرق، والمتوقَّع عند التصفير. أرقام فقط من plan_snapshots وusage_turns.

المنهج: النسبة في اللقطات عدد صحيح مقرَّب، فلا يُعرف منها إلا لحظات الانتقال (أول لقطة تحمل قيمة أعلى من سابقتها). الانتقال «دقيق»
إن سبقته لقطة قبل أقل من PRECISE_GAP ثانية، فزمن الصعود معروف ضمن تلك الفجوة؛ والفجوات الطويلة (نوم الحاسوب أو توقّف الجامع) تُسقط
الانتقال. تُجمع التوكنات المقاسة بين كل انتقالين دقيقين متتاليين صاعدين، والتقدير = مجموع التوكنات ÷ مجموع فروق النسبة (مرجّح بالحجم)،
ومعه الوسيط والمدى وعدد الأزواج. لا تقدير إن قلّت الأزواج عن MIN_PAIRS. الدقة محدودة بتقريب النسبة إلى 1%، فالمدى واسع في الأسابيع الأولى.
الترجيح بأسعار الأنواع (قراءة الذاكرة أرخص من المخرجات) لم يثبت على البيانات الحالية أنه يفسّر الحصة أفضل من الخام، فالمقياس هنا الخام.
التوقّع: معدل الحرق = توكنات آخر BURN_HOURS ساعة ÷ كلفة 1% ÷ الساعات؛ المتوقَّع عند التصفير = آخر نسبة + المعدل × الساعات المتبقية، وإن
تجاوز 100 فيُحسب وقت بلوغ 100 بالمعدل نفسه.
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


def pairs(con, pct_col, model_like=None):
    """أزواج انتقالين دقيقين متتاليين صاعدين: (من، إلى، فرق النسبة، التوكنات المقاسة بينهما)."""
    tr = transitions(con, pct_col)
    out = []
    for k in range(1, len(tr)):
        a, b = tr[k - 1], tr[k]
        d = b[3] - a[3]
        if a[4] and b[4] and d > 0 and b[3] > b[2]:
            out.append((a[1], b[1], d, _tokens(con, a[1], b[1], model_like)))
    return out


def cost(con, pct_col, model_like=None):
    """توكن لكل 1%: التقدير المرجّح والوسيط والمدى وعدد الأزواج، أو None إن قلّت الأزواج."""
    ps = pairs(con, pct_col, model_like)
    if len(ps) < MIN_PAIRS:
        return dict(n=len(ps), per_pct=None)
    per = sorted(t / d for _a, _b, d, t in ps)
    return dict(n=len(ps), per_pct=sum(t for *_x, t in ps) / sum(d for _a, _b, d, _t in ps), med=median(per), lo=per[0], hi=per[-1],
                span_from=ps[0][0], span_to=ps[-1][1])


def forecast(con, pct_col, resets_col, per_pct, model_like=None, now=None):
    """آخر نسبة وزمن تصفيرها، ومعدل الحرق (نسبة/يوم من توكنات آخر 24 ساعة ÷ كلفة 1%)، والمتوقَّع عند التصفير أو وقت بلوغ 100."""
    row = con.execute("SELECT ts, %s, %s FROM plan_snapshots WHERE %s IS NOT NULL ORDER BY ts DESC LIMIT 1" % (pct_col, resets_col, pct_col)).fetchone()
    if not row:
        return None
    ts, pct, resets = row
    out = dict(ts=ts, pct=pct, resets=resets, rate_day=None, at_reset=None, full_at=None)
    if per_pct is None:
        return out
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(hours=BURN_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tok = _tokens(con, since, now.strftime("%Y-%m-%dT%H:%M:%SZ"), model_like)
    rate_h = tok / per_pct / BURN_HOURS
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
