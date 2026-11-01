"""صفحة «الجلسات بالساعة» الذاتية: لكل دور من أدوار المشروع منحنى توكنات تراكمي وضغط سياق % على محور زمني ساعي. أرقام فقط.

جدول الحقائق H = دور × ساعة (UTC) × نموذج؛ الأدوار: أرقام المشروع 01xx–08xx (rp=1) وأي رقم آخر وفئات الجلسات بلا رقم بحسب مجلد العمل (rp=0، مخفية افتراضًا في الصفحة). الحقول:
  k = توكنات الساعة (إدخال + كتابة ذاكرة + قراءة ذاكرة + مخرجات، كل الردود بما فيها الوكلاء الفرعيون)،
  x = أكبر سياق لردّ رئيس في الساعة (بلا الوكلاء الفرعيين) وw نافذته الفعلية، d = عدد هبوطات السياق (تقدير الضغط/المسح)
  وdi منها ما جاء بعد خمول (فجوة > WAKE_GAP_SEC عن الردّ الرئيس السابق فقد يكون استئنافًا لا ضغطًا)، وأكبرها من df إلى dt.
الضغط % = السياق ÷ النافذة الفعلية للردّ: نظام الجلسة من regime (كما في sessions_page) ← 250 ألفًا لنظام W250 ومليون لغيره،
  و200 ألف لمجموعة النماذج الأقدم (haiku-4-5 وsonnet-4-6 أقصى سياقهما نحو 200 ألف) أيًّا كان النظام. WINDOW قيمة افتراضية واحتياطية.
هبوط السياق: ردّ سياقه أقل من نصف سابقه في الجلسة نفسها وكان السابق ≥ 100 ألف (استدلال، فـClaude Code لا يسجّل الضغط في سجلاتنا).
"""
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402
import regime  # noqa: E402
import role_groups  # noqa: E402
import sessions_page  # noqa: E402
import ui  # noqa: E402

WINDOW = 1_000_000
WINDOW_W250 = 250_000
WINDOW_OLD = 200_000  # النماذج الأقدم (مجموعة «أخرى (أقدم)»): نافذتها نحو 200 ألف لا مليون
ALERT_PCT = 80
_AUTOCOMPACT_RE = re.compile(r"autoCompactsAtPercent=(\d+)")


def _epoch(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def window_of(x, group):
    """النافذة الفعلية لردّ نظامه x (من regime) ومجموعة نموذجه group (من dashboard._group)."""
    if group == len(dashboard.MODEL_GROUPS):  # مجموعة «أخرى (أقدم)»
        return WINDOW_OLD
    return WINDOW_W250 if x == regime.W250 else WINDOW


def windows_meta(con, ch=None):
    """وصف النوافذ للصفحة: القيم الثلاث، وفترات نظام 250 ألفًا من config_changes، ونطاق نسبة الضغط التلقائي المذكور في ملاحظاتها."""
    ch = regime.changes() if ch is None else ch
    spans = [[ts, ch[i + 1][0] if i + 1 < len(ch) else None] for i, (ts, code) in enumerate(ch) if code == regime.W250]
    pcts = sorted({int(m) for (note,) in con.execute("SELECT note FROM config_changes") for m in _AUTOCOMPACT_RE.findall(note or "")})
    return dict(default=WINDOW, w250=WINDOW_W250, old=WINDOW_OLD, w250_spans=spans,
                autocompact_pct=[pcts[0], pcts[-1]] if pcts else None)


def payload(con):
    role = {k: role_groups.role_name(n, cwd) for k, n, cwd in con.execute("SELECT session_key, number, cwd FROM sessions")}
    roles, role_of = [], {}
    starts = {}  # session_key -> أزمنة بدء العمليات المعروفة (agent_starts)، مرتبة؛ كما في sessions_page
    for sid, st in con.execute("SELECT session_id, started_at FROM agent_starts ORDER BY started_at"):
        starts.setdefault(sid, []).append(st)
    ch = regime.changes()
    first_ts = {}
    facts = {}
    prev = {}  # session_key -> (epoch, ctx) لآخر ردّ رئيس
    cur = con.execute(
        "SELECT session_key, ts, model, input_tokens, cache_creation_tokens, cache_read_tokens, output_tokens, is_sidechain "
        "FROM usage_turns ORDER BY session_key, ts, message_id")
    for key, ts, model, i, cc, cr, u, side in cur:
        n = role.get(key) or role_groups.OTHER
        if n not in role_of:
            role_of[n] = len(roles)
            roles.append(n)
        first_ts.setdefault(key, ts)
        epoch = _epoch(ts)
        ctx = i + cc + cr
        group = dashboard._group(model)
        dfrom = dto = idle = 0
        if not side:
            p = prev.get(key)
            if p and p[1] >= sessions_page.DROP_MIN_PREV and ctx < sessions_page.DROP_RATIO * p[1]:
                dfrom, dto = p[1], ctx
                idle = int(epoch - p[0] > sessions_page.WAKE_GAP_SEC)
            prev[key] = (epoch, ctx)
        k = (role_of[n], int(epoch // 3600), group)
        r = facts.setdefault(k, [0, 0, 0, 0, 0, 0, 0])  # k, x, w, d, di, df, dt
        r[0] += ctx + u
        if not side and ctx > r[1]:
            r[1] = ctx
            r[2] = window_of(regime.classify(ts, first_ts[key], starts.get(key, []), ch), group)
        if dfrom:
            r[3] += 1
            r[4] += idle
            if dfrom > r[5]:
                r[5], r[6] = dfrom, dto
    rows = [dict(r=k[0], h=k[1], m=k[2], k=v[0], x=v[1], w=v[2], d=v[3], di=v[4], df=v[5], dt=v[6]) for k, v in sorted(facts.items())]
    plan = plan_rows(con)
    first, last = con.execute("SELECT MIN(substr(ts,1,10)), MAX(substr(ts,1,10)) FROM usage_turns").fetchone()
    return dict(models=[n for _m, n in dashboard.MODEL_GROUPS] + [dashboard.OTHER_NAME], window=WINDOW, windows=windows_meta(con, ch),
                alert=ALERT_PCT, drop_ratio=sessions_page.DROP_RATIO, drop_min=sessions_page.DROP_MIN_PREV, wake_gap=sessions_page.WAKE_GAP_SEC,
                first_day=first, last_day=last, roles=roles, rp=[int(role_groups.is_project(n)) for n in roles], h=rows, plan=plan)


def plan_rows(con):
    """لقطات الحصة بالشكل الذي تقرؤه الصفحة (D.plan)؛ يخدم البناء الثابت ونقطة /plan.json الحيّة."""
    return [dict(ts=ts, f=f, fr=fr, w=w, wr=wr, fa=fa, far=far, pl=pl, src=src) for ts, f, fr, w, wr, fa, far, pl, src in con.execute(
        "SELECT ts, five_hour_pct, five_hour_resets_at, seven_day_pct, seven_day_resets_at, fable_pct, fable_resets_at, plan, source "
        "FROM plan_snapshots ORDER BY ts")]


def render(data, stamp, page="hourly.html"):
    return ui.render(page, data, {"__STAMP__": stamp})


def write(path, data, stamp, page="hourly.html"):
    ui.write(path, render(data, stamp, page))
