"""صفحة «طلب جديد» (D-519م/D-521م): بديل محادثة المالك — تكتب ملفّاً في requests/ بقالب الاستلام نفسه، بصفر توكنز.

POST /request في serve.py ينادي submit(): يتحقّق من الحقول ويكتب requests/<طابع>-<رقم>.md؛ ولا يتصل بنموذج ولا بالدفتر
(الاستلام في delivery_manager_work/tools/runner.py يحوّل الملفّ بطاقةً في دورته التالية).
"""
import hashlib
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui  # noqa: E402

SIZES = ("صغير", "متوسط", "كبير", "تصميم")
PRIORITIES = ("P1", "P2", "P3")
TOUCHES = ("الصلاحيات", "الأدوار", "الأمن", "الهجرات")
APPROVALS = ("مباشر", "معاينة")  # D-528م: نشر مباشر بعد البوّابة، أو معاينة على 8500 قبل الدمج
MAX = {"title": 120, "ask": 1500, "accept": 1500}
MAX_BODY = 20000  # سقف جسم JSON بالبايت؛ فوقه 413 قبل قراءة الجسم
RATE_PER_HOUR = 20
DEFAULT_DIR = Path.home() / "delivery_manager_work" / "requests"


class RateLimit:
    """حدّ طلباتٍ في الساعة بنافذةٍ منزلقة في الذاكرة (خادمٌ محلّيّ واحد)."""

    def __init__(self, per_hour, clock=time.time):
        self.per_hour, self.clock, self.hits = per_hour, clock, []

    def allow(self):
        now = self.clock()
        self.hits = [t for t in self.hits if now - t < 3600]
        if len(self.hits) >= self.per_hour:
            return False
        self.hits.append(now)
        return True


class ValidationError(ValueError):
    """رفضُ حقل: الرسالة عربيّة و.field اسمُ الحقل (للردّ {"error","field"})."""

    def __init__(self, message, field=""):
        super().__init__(message)
        self.field = field


ALLOWED_KEYS = frozenset({"title", "ask", "accept", "size", "priority", "touches", "approval"})
_PII = None


def pii_pattern():
    """تعبيرُ البيانات الشخصيّة نفسُه في سجلّ المايسترو (مصدرٌ واحد)؛ يغيب فيُتخطّى بتسجيلٍ صريح لا بصمت."""
    global _PII
    if _PII is None:
        import importlib.util
        src = Path(os.environ.get("MAESTRO_LEDGER") or Path.home() / "delivery_manager_work" / "tools" / "ledger.py")
        if not src.is_file():
            raise OSError("تعذّر تحميل فاحص البيانات الشخصية: " + str(src))
        spec = importlib.util.spec_from_file_location("maestro_ledger_pii", src)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(src.parent))
        spec.loader.exec_module(mod)
        _PII = mod._PII
    return _PII


def requests_dir():
    return Path(os.environ.get("RUNNER_REQUESTS") or DEFAULT_DIR)


def _clean(v, limit):
    return re.sub(r"[\r\n]+", " ", str(v or "")).strip()[:limit]


def validate(params):
    """يعيد حقولاً نظيفة أو يرفع ValidationError برسالة عربيّة وحقل؛ مفاتيحٌ مجهولة ← رفض، ولا ملءَ صامت لأيّ حقل."""
    unknown = sorted(set(params) - ALLOWED_KEYS)
    if unknown:
        raise ValidationError("حقلٌ غير معروف: " + "، ".join(unknown), unknown[0])
    title, ask = _clean(params.get("title"), MAX["title"]), _clean(params.get("ask"), MAX["ask"])
    raw = params.get("accept") or []
    lines = [_clean(x, MAX["accept"]) for x in (raw.splitlines() if isinstance(raw, str) else raw)]
    lines = [x for x in lines if x]
    size, prio = str(params.get("size") or ""), str(params.get("priority") or "")
    approval = str(params.get("approval") or ("معاينة" if size == "تصميم" else "مباشر"))
    if approval not in APPROVALS:
        raise ValidationError("قيمة «الاعتماد» غير صالحة", "approval")
    touches = params.get("touches") or []
    if not isinstance(touches, list) or any(t not in TOUCHES for t in touches):
        raise ValidationError("قيمة «يمسّ» غير صالحة", "touches")
    for field, label, ok in (("title", "العنوان", title), ("ask", "المطلوب", ask), ("accept", "معايير القبول", lines)):
        if not ok:
            raise ValidationError("الحقل ناقص: " + label, field)
    if size not in SIZES:
        raise ValidationError("الوسم غير صالح", "size")
    if prio not in PRIORITIES:
        raise ValidationError("اختر الأولوية", "priority")
    pii = pii_pattern()
    for field, text in (("title", title), ("ask", ask), ("accept", " ".join(lines))):
        if pii.search(text):
            raise ValidationError("يبدو في الحقل رقم هوية أو بريد؛ تُمنع البيانات الشخصية", field)
    return dict(title=title, ask=ask, accept=" ؛ ".join(lines), size=size, priority=prio, touches=touches, approval=approval)


def submit(params, now=None):
    """يكتب الطلب ذرّياً (ملف مؤقت في .incoming ثم os.replace) ويعيد {ok, file}؛ ValidationError عند الرفض ولا ملفَّ جزئياً يراه المشغّل."""
    fields = validate(params)
    d = requests_dir()
    (d / ".incoming").mkdir(parents=True, exist_ok=True)
    t = now or time.localtime()
    stamp = time.strftime("%Y%m%d-%H%M%S", t)
    path = d / ("web-%s.md" % stamp)
    n = 1
    while path.exists():
        n += 1
        path = d / ("web-%s-%d.md" % (stamp, n))
    body = "العنوان: %s\nالمطلوب: %s\nمعايير القبول: %s\nالوسم: %s\nالأولوية: %s\n" % (
        fields["title"], fields["ask"], fields["accept"], fields["size"], fields["priority"])
    body += "الاعتماد: %s\n" % fields["approval"]
    if fields["touches"]:
        body += "يمسّ: %s\n" % "، ".join(fields["touches"])
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    body += "مقدَّم في: %s\nالمصدر: mizan-form\nsha256: %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S", t), digest)
    tmp = d / ".incoming" / (path.name + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)
    return dict(ok=True, file=path.name)


def payload():
    return dict(request=dict(api="request", sizes=list(SIZES), priorities=list(PRIORITIES), touches=list(TOUCHES), approvals=list(APPROVALS)))


