"""صفحة «الجلسات بالساعة» الذاتية: لكل دور من أدوار المشروع منحنى توكنات تراكمي وضغط سياق % على محور زمني ساعي. أرقام فقط.

جدول الحقائق H = دور × ساعة (UTC) × نموذج؛ الأدوار: أرقام المشروع 01xx–08xx (rp=1) وأي رقم آخر وفئات الجلسات بلا رقم بحسب مجلد العمل (rp=0، مخفية افتراضًا في الصفحة). الحقول:
  k = توكنات الساعة (إدخال + كتابة ذاكرة + قراءة ذاكرة + مخرجات، كل الردود بما فيها الوكلاء الفرعيون)،
  x = أكبر سياق لردّ رئيس في الساعة (بلا الوكلاء الفرعيين)، d = عدد هبوطات السياق (تقدير الضغط/المسح) وأكبرها من df إلى dt.
الضغط % = السياق ÷ نافذة افتراضية قدرها WINDOW توكن (افتراض يُعلَن في الصفحة، وليس قياسًا لنافذة النموذج الفعلية).
هبوط السياق: ردّ سياقه أقل من نصف سابقه في الجلسة نفسها وكان السابق ≥ 100 ألف (استدلال، فـClaude Code لا يسجّل الضغط في سجلاتنا).
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402
import role_groups  # noqa: E402
import sessions_page  # noqa: E402
import ui  # noqa: E402

WINDOW = 1_000_000
ALERT_PCT = 80


def _epoch(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def payload(con):
    role = {k: role_groups.role_name(n, cwd) for k, n, cwd in con.execute("SELECT session_key, number, cwd FROM sessions")}
    roles, role_of = [], {}
    facts = {}
    prev = {}  # session_key -> (epoch, ctx)
    cur = con.execute(
        "SELECT session_key, ts, model, input_tokens, cache_creation_tokens, cache_read_tokens, output_tokens, is_sidechain "
        "FROM usage_turns ORDER BY session_key, ts, message_id")
    for key, ts, model, i, cc, cr, u, side in cur:
        n = role.get(key) or role_groups.OTHER
        if n not in role_of:
            role_of[n] = len(roles)
            roles.append(n)
        epoch = _epoch(ts)
        ctx = i + cc + cr
        dfrom = dto = 0
        if not side:
            p = prev.get(key)
            if p and p[1] >= sessions_page.DROP_MIN_PREV and ctx < sessions_page.DROP_RATIO * p[1]:
                dfrom, dto = p[1], ctx
            prev[key] = (epoch, ctx)
        k = (role_of[n], int(epoch // 3600), dashboard._group(model))
        r = facts.setdefault(k, [0, 0, 0, 0, 0])  # k, x, d, df, dt
        r[0] += ctx + u
        if not side and ctx > r[1]:
            r[1] = ctx
        if dfrom:
            r[2] += 1
            if dfrom > r[3]:
                r[3], r[4] = dfrom, dto
    rows = [dict(r=k[0], h=k[1], m=k[2], k=v[0], x=v[1], d=v[2], df=v[3], dt=v[4]) for k, v in sorted(facts.items())]
    plan = [dict(ts=ts, f=f, fr=fr, w=w, wr=wr, fa=fa, src=src) for ts, f, fr, w, wr, fa, src in con.execute(
        "SELECT ts, five_hour_pct, five_hour_resets_at, seven_day_pct, seven_day_resets_at, fable_pct, source FROM plan_snapshots ORDER BY ts")]
    first, last = con.execute("SELECT MIN(substr(ts,1,10)), MAX(substr(ts,1,10)) FROM usage_turns").fetchone()
    return dict(models=[n for _m, n in dashboard.MODEL_GROUPS] + [dashboard.OTHER_NAME], window=WINDOW, alert=ALERT_PCT,
                drop_ratio=sessions_page.DROP_RATIO, drop_min=sessions_page.DROP_MIN_PREV,
                first_day=first, last_day=last, roles=roles, rp=[int(role_groups.is_project(n)) for n in roles], h=rows, plan=plan)


def render(data, stamp):
    return ui.render("hourly.html", data, {"__STAMP__": stamp})


def write(path, data, stamp):
    ui.write(path, render(data, stamp))
