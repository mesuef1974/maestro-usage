"""لوحة تفاعلية ذاتية (ملف HTML واحد بلا شبكة ولا مكتبات) من جداول القاعدة. أرقام ومعرّفات فقط؛ لا نصوص محادثات.

الحمولة جدولان للحقائق: A = يوم × نموذج × أصل الدور، وB = جلسة × يوم × نموذج، إضافةً إلى لقطات الخطة وتغييرات الإعدادات.
المرشِّحات (فترة، نماذج) تُحسب في المتصفح من هذين الجدولين، فتتّفق كل الأرقام.
في الحقيقتين الحقول t/i/cc/cr/u/v مجاميع كل الردود (الاستهلاك)، والحقول المسبوقة بـm (mt/mi/mcc/mcr/mv) للخيط الرئيس وحده
(is_sidechain=0) لأن مقاييس الضغط (متوسط السياق وفوق العتبة وأكبر سياق) تُحسب من الردود الرئيسة فقط كما في تعريف «سياق الردّ».
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hourly_page  # noqa: E402
import quota_model  # noqa: E402
import ui  # noqa: E402

THRESHOLD = 300_000  # يطابق reports.CTX_THRESHOLD
PLAN_LABEL = "Ultra"  # اسم الخطة (كانت «Max 20x» حتى 2026-10-30؛ القاعدة تحفظ «Max» فقط)
PLAN_RENEW_DAY = None  # يوم تجديد الاشتراك الشهري (1-31)؛ None = لا يُعرض سطر التجديد

# ترتيب ثابت: اللون يتبع النموذج لا رتبته. الباقي يُطوى في «أخرى».
MODEL_GROUPS = [
    ("claude-sonnet-5-5", "Sonnet 5.5"), ("claude-sonnet-5", "Sonnet 5"), ("claude-opus-5", "Opus 5"),
    ("claude-opus-5-5", "Opus 5.5"), ("claude-fable-5-1", "Fable 5.1"), ("claude-haiku-5-5", "Haiku 5.5"),
]
OTHER_NAME = "أخرى (أقدم)"
ORIGINS = ("human", "peer", "scheduled", "sdk", "task_notification", "system", "sub", "unknown")  # sub = ردود الوكلاء الفرعيين


def _group(model):
    for i, (mid, _name) in enumerate(MODEL_GROUPS):
        if model == mid:
            return i
    return len(MODEL_GROUPS)


def _origin(o):
    return o if o in ORIGINS else "unknown"


def payload(con, not_applied_mark, min_turns):
    ctx = "(input_tokens + cache_creation_tokens + cache_read_tokens)"
    over = "CASE WHEN %s > ? THEN 1 ELSE 0 END" % ctx  # الردّ فوق العتبة
    main = "CASE WHEN is_sidechain=0 THEN %s ELSE 0 END"  # الكمية للخيط الرئيس فقط
    # الأصل: ردود الوكلاء الفرعيين أصلها «sub» (لا أصل مسجّل لها أصلًا)، وما سواها بلا أصل «unknown»
    origin = "CASE WHEN is_sidechain=1 THEN 'sub' ELSE COALESCE(turn_origin,'unknown') END"
    sums = "COUNT(*), SUM(input_tokens), SUM(cache_creation_tokens), SUM(cache_read_tokens), SUM(output_tokens), SUM(%s)" % over
    main_sums = ", ".join("SUM(%s)" % (main % x) for x in ("1", "input_tokens", "cache_creation_tokens", "cache_read_tokens", over))
    a = {}
    for day, model, org, *vals in con.execute(
            "SELECT substr(ts,1,10), model, %s, %s, %s FROM usage_turns GROUP BY 1, 2, 3" % (origin, sums, main_sums), (THRESHOLD, THRESHOLD)):
        k = (day, _group(model), _origin(org))
        r = a.setdefault(k, [0] * 11)  # 0-5 كل الردود (t i cc cr u v)، 6-10 الخيط الرئيس (mt mi mcc mcr mv)
        for j, x in enumerate(vals):
            r[j] += x or 0
    fact_a = [dict(d=k[0], m=k[1], g=k[2], t=r[0], i=r[1], cc=r[2], cr=r[3], u=r[4], v=r[5], mt=r[6], mi=r[7], mcc=r[8], mcr=r[9], mv=r[10])
              for k, r in sorted(a.items())]

    plan = hourly_page.plan_rows(con)  # مصدر واحد للقطات (مرقَّقة) يخدم الصفحة و/plan.json
    changes = [dict(ts=ts, key=key, old=old, new=new, applied=not_applied_mark not in (note or ""))
               for ts, key, old, new, note in con.execute(
                   "SELECT ts, key, old_value, new_value, note FROM config_changes ORDER BY ts, id")]
    first, last = con.execute("SELECT MIN(substr(ts,1,10)), MAX(substr(ts,1,10)) FROM usage_turns").fetchone()
    return dict(models=[n for _m, n in MODEL_GROUPS] + [OTHER_NAME], threshold=THRESHOLD, min_turns=min_turns,
                first_day=first, last_day=last, a=fact_a, plan=plan, changes=changes,
                plan_label=PLAN_LABEL, plan_renew_day=PLAN_RENEW_DAY, quota=quota_model.payload(con))


