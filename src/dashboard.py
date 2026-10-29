"""لوحة تفاعلية ذاتية (ملف HTML واحد بلا شبكة ولا مكتبات) من جداول القاعدة. أرقام ومعرّفات فقط؛ لا نصوص محادثات.

الحمولة جدولان للحقائق: A = يوم × نموذج × أصل الدور، وB = جلسة × يوم × نموذج، إضافةً إلى لقطات الخطة وتغييرات الإعدادات.
المرشِّحات (فترة، نماذج) تُحسب في المتصفح من هذين الجدولين، فتتّفق كل الأرقام.
"""
import json
import os
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent / "dashboard.html"
THRESHOLD = 300_000  # يطابق reports.CTX_THRESHOLD

# ترتيب ثابت: اللون يتبع النموذج لا رتبته. الباقي يُطوى في «أخرى».
MODEL_GROUPS = [
    ("claude-sonnet-5-5", "Sonnet 5.5"), ("claude-sonnet-5", "Sonnet 5"), ("claude-opus-5", "Opus 5"),
    ("claude-opus-5-5", "Opus 5.5"), ("claude-fable-5-1", "Fable 5.1"), ("claude-haiku-5-5", "Haiku 5.5"),
]
OTHER_NAME = "أخرى (أقدم)"
ORIGINS = ("human", "peer", "scheduled", "sdk", "task_notification", "system", "unknown")


def _group(model):
    for i, (mid, _name) in enumerate(MODEL_GROUPS):
        if model == mid:
            return i
    return len(MODEL_GROUPS)


def _origin(o):
    return o if o in ORIGINS else "unknown"


def payload(con, label_fn, not_applied_mark, min_turns):
    ctx = "(input_tokens + cache_creation_tokens + cache_read_tokens)"
    a = {}
    for day, model, org, t, i, cc, cr, u, v in con.execute(
            "SELECT substr(ts,1,10), model, COALESCE(turn_origin,'unknown'), COUNT(*), SUM(input_tokens), SUM(cache_creation_tokens), "
            "SUM(cache_read_tokens), SUM(output_tokens), SUM(CASE WHEN %s > ? THEN 1 ELSE 0 END) FROM usage_turns "
            "GROUP BY 1, 2, 3" % ctx, (THRESHOLD,)):
        k = (day, _group(model), _origin(org))
        r = a.setdefault(k, [0] * 6)
        for j, x in enumerate((t, i, cc, cr, u, v)):
            r[j] += x or 0
    fact_a = [dict(d=k[0], m=k[1], g=k[2], t=r[0], i=r[1], cc=r[2], cr=r[3], u=r[4], v=r[5]) for k, r in sorted(a.items())]

    b = {}
    for key, day, model, t, i, cc, cr, u, v, mx, cv in con.execute(
            "SELECT session_key, substr(ts,1,10), model, COUNT(*), SUM(input_tokens), SUM(cache_creation_tokens), SUM(cache_read_tokens), "
            "SUM(output_tokens), SUM(CASE WHEN %s > ? THEN 1 ELSE 0 END), MAX(%s), SUM(CASE WHEN %s > ? THEN %s ELSE 0 END) "
            "FROM usage_turns GROUP BY 1, 2, 3" % (ctx, ctx, ctx, ctx), (THRESHOLD, THRESHOLD)):
        k = (key, day, _group(model))
        r = b.setdefault(k, [0] * 8)  # 0-5 مجاميع، 6 أكبر سياق، 7 مجموع سياق الردود فوق العتبة
        for j, x in enumerate((t, i, cc, cr, u, v)):
            r[j] += x or 0
        r[6] = max(r[6], mx or 0)
        r[7] += cv or 0
    keys = sorted({k[0] for k in b})
    meta = {r[0]: r for r in con.execute("SELECT session_key, COALESCE(number,''), COALESCE(cwd,'') FROM sessions")}
    index = {key: n for n, key in enumerate(keys)}
    sessions = [dict(label=label_fn(meta.get(key, (key, "", ""))[1], key, meta.get(key, (key, "", ""))[2])) for key in keys]
    fact_b = [dict(s=index[k[0]], d=k[1], m=k[2], t=r[0], i=r[1], cc=r[2], cr=r[3], u=r[4], v=r[5], mx=r[6], cv=r[7])
              for k, r in sorted(b.items())]

    plan = [dict(ts=ts, f=f, w=w, src=src) for ts, f, w, src in con.execute(
        "SELECT ts, five_hour_pct, seven_day_pct, source FROM plan_snapshots ORDER BY ts")]
    changes = [dict(ts=ts, key=key, old=old, new=new, applied=not_applied_mark not in (note or ""))
               for ts, key, old, new, note in con.execute(
                   "SELECT ts, key, old_value, new_value, note FROM config_changes ORDER BY ts, id")]
    first, last = con.execute("SELECT MIN(substr(ts,1,10)), MAX(substr(ts,1,10)) FROM usage_turns").fetchone()
    return dict(models=[n for _m, n in MODEL_GROUPS] + [OTHER_NAME], threshold=THRESHOLD, min_turns=min_turns,
                first_day=first, last_day=last, a=fact_a, b=fact_b, sessions=sessions, plan=plan, changes=changes)


def render(data, static_html, stamp):
    """يملأ القالب. JSON يُهرَّب منه '</' كي لا يُغلق وسم script."""
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    page = TEMPLATE.read_text(encoding="utf-8")
    for token, value in (("__STAMP__", stamp), ("__STATIC__", static_html), ("__DATA__", blob)):
        assert token in page, token
        page = page.replace(token, value, 1)
    return page


def write(path, data, static_html, stamp):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(render(data, static_html, stamp))
    os.replace(tmp, path)
