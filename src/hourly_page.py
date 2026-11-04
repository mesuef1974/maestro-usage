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
    spans = []
    pcts = sorted({int(m) for (note,) in con.execute("SELECT note FROM config_changes") for m in _AUTOCOMPACT_RE.findall(note or "")})
    return dict(default=WINDOW, w250=WINDOW_W250, old=WINDOW_OLD, w250_spans=spans,
                autocompact_pct=[pcts[0], pcts[-1]] if pcts else None)


def payload(con):
    """توكنات كل ساعة × مجموعة نموذج (بعد الاعتماد على جلسة واحدة لا بُعد دور): r دائمًا 0 ليبقى شكل الصفوف كما يقرؤه القالب."""
    facts = {}
    for ts, model, i, cc, cr, u in con.execute(
            "SELECT ts, model, input_tokens, cache_creation_tokens, cache_read_tokens, output_tokens FROM usage_turns ORDER BY ts"):
        k = (int(_epoch(ts) // 3600), dashboard._group(model))
        facts[k] = facts.get(k, 0) + i + cc + cr + u
    rows = [dict(r=0, h=h, m=m, k=v, x=0, w=WINDOW, d=0, di=0, df=0, dt=0) for (h, m), v in sorted(facts.items())]
    first, last = con.execute("SELECT MIN(substr(ts,1,10)), MAX(substr(ts,1,10)) FROM usage_turns").fetchone()
    return dict(models=[n for _m, n in dashboard.MODEL_GROUPS] + [dashboard.OTHER_NAME], window=WINDOW, windows=windows_meta(con),
                alert=ALERT_PCT, drop_ratio=0.5, drop_min=100000, wake_gap=3600,
                first_day=first, last_day=last, roles=["الكل"], rp=[1], h=rows, plan=plan_rows(con))


def plan_rows(con):
    """لقطات الحصة بالشكل الذي تقرؤه الصفحة (D.plan)؛ يخدم البناء الثابت ونقطة /plan.json الحيّة."""
    return [dict(ts=ts, f=f, fr=fr, w=w, wr=wr, fa=fa, far=far, pl=pl, src=src) for ts, f, fr, w, wr, fa, far, pl, src in con.execute(
        "SELECT ts, five_hour_pct, five_hour_resets_at, seven_day_pct, seven_day_resets_at, fable_pct, fable_resets_at, plan, source "
        "FROM plan_snapshots ORDER BY ts")]


def render(data, stamp, page="hourly.html"):
    return ui.render(page, data, {"__STAMP__": stamp})


def write(path, data, stamp, page="hourly.html"):
    ui.write(path, render(data, stamp, page))
