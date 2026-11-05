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

SIZES = ("صغير", "متوسط", "كبير")  # المعروض في الاستمارة؛ يحدّد النموذج في المشغّل
LEGACY_SIZES = ("تصميم",)  # مقبول من الطلبات القديمة (يُقرأ «تحسين واجهة» حجمه كبير)
PRIORITIES = ("P1", "P2", "P3")
TOUCHES = ("الصلاحيات", "الأدوار", "الأمن", "الهجرات")
# مصدر واحد لما «يمسّ»: الأنماط نفسها في FORBIDDEN_GLOBS ببوّابة الدمج (scripts/auto_merge_gate.py في shschool_mvp)؛ اختبار يتحقق من التطابق
TOUCH_GLOBS = {"الأمن": ("*/security/*", "security/*"), "الصلاحيات": ("*permissions*",), "الهجرات": ("*/migrations/*",),
               "الأدوار": ("*rbac*", "*roles*", "*Role*")}
APPROVALS = ("مباشر", "معاينة")  # D-528م: نشر مباشر بعد البوّابة، أو معاينة على 8500 قبل الدمج
MAX = {"title": 120, "ask": 1500, "accept": 1500, "page": 200, "file": 200, "out_of_scope": 500}
MAX_FILES = 20
MAX_BODY = 20000  # سقف جسم JSON بالبايت؛ فوقه 413 قبل قراءة الجسم
RATE_PER_HOUR = 20
DEFAULT_DIR = Path.home() / "delivery_manager_work" / "requests"
CRITERIA_PATH = Path(__file__).resolve().parent / "request_criteria.json"
REPO = Path(os.environ.get("MIZAN_REPO") or "D:/shschool_mvp")  # مستودع المنصّة: مصدر إكمال «الملفات المتوقَّعة»
LEDGER_EVENTS = Path(os.environ.get("MAESTRO_EVENTS") or Path.home() / "delivery_manager_work" / "ledger" / "events.jsonl")
VAGUE = ("حسّن", "حسن", "رتّب", "رتب", "طوّر", "طور", "عدّل", "عدل", "اصلح", "أصلح")
SAFE_PATH = re.compile(r"^[\w.\-/]+$")


def criteria_lib():
    """مكتبة المعايير والأنواع من request_criteria.json (بيانات لا شيفرة)."""
    import json
    d = json.loads(CRITERIA_PATH.read_text(encoding="utf-8"))
    d["by_id"] = {c["id"]: c for c in d["criteria"]}
    return d


TYPES = tuple(criteria_lib()["types"])


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


ALLOWED_KEYS = frozenset({"title", "ask", "accept", "size", "priority", "touches", "approval", "type", "criteria", "page", "files", "out_of_scope"})
_PII = None
PII_SOURCE = None  # "ledger" حين يُحمَّل من سجلّ المايسترو، أو "fallback" حين يغيب (نسخة مطابقة هنا)
# نسخةٌ مطابقة لتعبير سجلّ المايسترو (tools/ledger.py: _PII) تُستعمل إن غاب السجلّ، فلا تتعطّل صفحة الطلب ولا اختباراتها خارج جهاز المالك
_PII_FALLBACK = re.compile(r"\b\d{9,}\b|[\w.+-]+@[\w-]+\.[\w.]+")


def ledger_source():
    return Path(os.environ.get("MAESTRO_LEDGER") or Path.home() / "delivery_manager_work" / "tools" / "ledger.py")


def pii_pattern():
    """تعبيرُ البيانات الشخصيّة من سجلّ المايسترو إن وُجد (المصدرُ الأصل)، وإلا النسخةُ المطابقة هنا مع تسجيل المصدر في PII_SOURCE."""
    global _PII, PII_SOURCE
    if _PII is None:
        src = ledger_source()
        if src.is_file():
            import importlib.util
            spec = importlib.util.spec_from_file_location("maestro_ledger_pii", src)
            mod = importlib.util.module_from_spec(spec)
            sys.path.insert(0, str(src.parent))
            spec.loader.exec_module(mod)
            _PII, PII_SOURCE = mod._PII, "ledger"
        else:
            _PII, PII_SOURCE = _PII_FALLBACK, "fallback"
    return _PII


def requests_dir():
    return Path(os.environ.get("RUNNER_REQUESTS") or DEFAULT_DIR)


def _clean(v, limit):
    return re.sub(r"[\r\n]+", " ", str(v or "")).strip()[:limit]


def _clean_multiline(v, limit):
    """النص متعدد الأسطر يُحفظ في سطر واحد (صيغة الملف: سطر لكل مفتاح) بفاصل « / » فلا تضيع بنية القالب."""
    lines = [ln.strip() for ln in str(v or "").splitlines()]
    return " / ".join(ln for ln in lines if ln)[:limit]


def touches_for_files(files):
    """الخانات التي تمسّها الملفات المعلنة بأنماط البوّابة نفسها (التوجيه المبكر 3.1 من جهة الاستمارة)."""
    from fnmatch import fnmatch
    return sorted({t for f in files for t, globs in TOUCH_GLOBS.items() if any(fnmatch(f, g) for g in globs)}, key=TOUCHES.index)


def readiness(f):
    """مقياس الجاهزية (2.4): ملاحظات لا تمنع الإرسال. الشروط الصلبة لالتقاط المشغّل (pick_card) يضمنها validate نفسه."""
    notes = []
    if len(f["title"].split()) < 3:
        notes.append("العنوان أقل من ثلاث كلمات")
    if len(f["ask"]) < 120:
        notes.append("المطلوب أقصر من 120 حرفًا")
    if len(f["accept_list"]) < 2:
        notes.append("معيار قبول واحد فقط")
    if f["type"] in ("خلل", "تحسين واجهة") and not (f["page"] or f["files"]):
        notes.append("حدّد الصفحة أو الملفات لهذا النوع")
    words = re.findall(r"[\w\u0600-\u06FF]+", f["title"] + " " + f["ask"])
    if words and all(w in VAGUE for w in words[:2]) and len(words) <= 4:
        notes.append("فعل مبهم وحده (حسّن، رتّب، طوّر، عدّل)")
    return notes


def validate(params):
    """يعيد حقولاً نظيفة أو يرفع ValidationError برسالة عربيّة وحقل؛ مفاتيحٌ مجهولة ← رفض، ولا ملءَ صامت لأيّ حقل."""
    unknown = sorted(set(params) - ALLOWED_KEYS)
    if unknown:
        raise ValidationError("حقلٌ غير معروف: " + "، ".join(unknown), unknown[0])
    lib = criteria_lib()
    title, ask = _clean(params.get("title"), MAX["title"]), _clean_multiline(params.get("ask"), MAX["ask"])
    size, prio = str(params.get("size") or ""), str(params.get("priority") or "")
    rtype = str(params.get("type") or "")
    if rtype not in lib["types"]:
        raise ValidationError("اختر نوع الطلب", "type")
    raw = params.get("accept") or []
    extra = [_clean(x, MAX["accept"]) for x in (raw.splitlines() if isinstance(raw, str) else raw)]
    extra = [x for x in extra if x]
    ids = params.get("criteria") or []
    if not isinstance(ids, list) or any(isinstance(i, bool) or not isinstance(i, int) or i not in lib["by_id"] for i in ids):
        raise ValidationError("معيار قبول غير معروف", "criteria")
    ids = sorted(set(ids))
    chosen = [lib["by_id"][i]["text"] for i in ids]
    approval = str(params.get("approval") or ("معاينة" if size in LEGACY_SIZES else lib["types"][rtype]["approval"]))
    if approval not in APPROVALS:
        raise ValidationError("قيمة «الاعتماد» غير صالحة", "approval")
    touches = params.get("touches") or []
    if not isinstance(touches, list) or any(t not in TOUCHES for t in touches):
        raise ValidationError("قيمة «يمسّ» غير صالحة", "touches")
    page = _clean(params.get("page"), MAX["page"])
    files = params.get("files") or []
    if isinstance(files, str):
        files = [x for x in re.split(r"[\n,،]+", files)]
    if not isinstance(files, list) or len(files) > MAX_FILES:
        raise ValidationError("الملفات المتوقَّعة: %d على الأكثر" % MAX_FILES, "files")
    files = [_clean(x, MAX["file"]).replace("\\", "/").lstrip("/") for x in files]
    files = [x for x in files if x]
    if any(".." in x.split("/") or not SAFE_PATH.match(x) for x in files):
        raise ValidationError("مسار ملف غير صالح (أحرف لاتينية وأرقام و/ و. و- فقط، بلا ..)", "files")
    out_of_scope = _clean(params.get("out_of_scope"), MAX["out_of_scope"])
    for field, label, ok in (("title", "العنوان", title), ("ask", "المطلوب", ask), ("accept", "معايير القبول", chosen + extra)):
        if not ok:
            raise ValidationError("الحقل ناقص: " + label, "criteria" if field == "accept" else field)
    if size not in SIZES + LEGACY_SIZES:
        raise ValidationError("اختر الحجم", "size")
    if prio not in PRIORITIES:
        raise ValidationError("اختر الأولوية", "priority")
    pii = pii_pattern()
    for field, text in (("title", title), ("ask", ask), ("accept", " ".join(extra)), ("page", page), ("out_of_scope", out_of_scope)):
        if pii.search(text):
            raise ValidationError("يبدو في الحقل رقم هوية أو بريد؛ تُمنع البيانات الشخصية", field)
    auto = [t for t in touches_for_files(files) if t not in touches]
    touches = sorted(set(touches) | set(auto), key=TOUCHES.index)
    checks = [lib["by_id"][i]["verify"]["check"] for i in ids if lib["by_id"][i]["verify"].get("auto") == "runner"]
    accept_list = chosen + extra
    return dict(title=title, ask=ask, accept=" ؛ ".join(accept_list), accept_list=accept_list, size=size, priority=prio, touches=touches,
                auto_touches=auto, approval=approval, type=rtype, criteria=ids, checks=checks, page=page, files=files, out_of_scope=out_of_scope)


def render_body(fields):
    """نصّ ملف الطلب كما يقرؤه المشغّل (intake_requests): سطر لكل مفتاح؛ المفاتيح القديمة أولًا كما هي فلا ينكسر الالتقاط."""
    body = "العنوان: %s\nالمطلوب: %s\nمعايير القبول: %s\nالوسم: %s\nالأولوية: %s\n" % (
        fields["title"], fields["ask"], fields["accept"], fields["size"], fields["priority"])
    body += "الاعتماد: %s\n" % fields["approval"]
    if fields["touches"]:
        body += "يمسّ: %s\n" % "، ".join(fields["touches"])
    body += "النوع: %s\n" % fields["type"]
    if fields["criteria"]:
        body += "معايير مرقّمة: %s\n" % "، ".join(str(i) for i in fields["criteria"])
    if fields["checks"]:
        body += "فحوص المشغّل: %s\n" % "، ".join(fields["checks"])
    if fields["page"]:
        body += "الصفحة: %s\n" % fields["page"]
    if fields["files"]:
        body += "الملفات: %s\n" % "، ".join(fields["files"])
    if fields["out_of_scope"]:
        body += "خارج النطاق: %s\n" % fields["out_of_scope"]
    return body


def preview(params):
    """معاينة بلا كتابة (2.5): نصّ الملف كما سيقرؤه المشغّل وملاحظات الجاهزية والخانات المضافة من الملفات."""
    f = validate(params)
    return dict(ok=True, body=render_body(f), readiness=readiness(f), auto_touches=f["auto_touches"])


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
    body = render_body(fields)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    body += "مقدَّم في: %s\nالمصدر: mizan-form\nsha256: %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S", t), digest)
    tmp = d / ".incoming" / (path.name + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)
    return dict(ok=True, file=path.name, auto_touches=fields["auto_touches"])


_FILES_CACHE = {"t": 0.0, "files": []}


def repo_files(now=None):
    """ملفات مستودع المنصّة من git ls-files، مخزّنة ساعة؛ فشلها (لا git أو لا مستودع) ← قائمة فارغة."""
    import subprocess
    now = now or time.time()
    if now - _FILES_CACHE["t"] < 3600 and _FILES_CACHE["files"]:
        return _FILES_CACHE["files"]
    try:
        r = subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True, encoding="utf-8", timeout=20,
                           stdin=subprocess.DEVNULL, creationflags=0x08000000 if sys.platform == "win32" else 0)
        files = [ln for ln in r.stdout.splitlines() if ln] if r.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        files = []
    _FILES_CACHE.update(t=now, files=files)
    return files


def match_files(q, files=None, limit=20):
    """إكمال تلقائي: يطابق كل كلمات q (بلا حساسية حالة) في المسار؛ الأقصر أولًا."""
    words = [w for w in str(q or "").lower().replace("\\", "/").split() if w]
    if not words:
        return []
    files = repo_files() if files is None else files
    hits = [f for f in files if all(w in f.lower() for w in words)]
    return sorted(hits, key=lambda f: (len(f), f))[:limit]


_AR_NORM = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ـ": None})


def norm_words(text):
    """كلمات للمقارنة: بلا تشكيل، وتوحيد الألف والياء والتاء المربوطة، وبلا كلمات من حرفين فأقل."""
    t = re.sub(r"[\u064B-\u0652\u0670]", "", str(text or "")).translate(_AR_NORM).lower()
    return {w for w in re.findall(r"[\w\u0600-\u06FF]+", t) if len(w) > 2}


CLOSED_STATES = ("closed", "published", "deferred", "merged")  # مثل RELEASING_STATES في ledger.py مع merged (لا يُعاد طلبه)


def open_cards(path=None):
    """بطاقات الدفتر المفتوحة (id، العنوان، الحالة) بقراءة events.jsonl فقط؛ غياب الدفتر ← []."""
    import json
    path = Path(path or LEDGER_EVENTS)
    cards = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                cid, data = e.get("id"), e.get("data") or {}
                if not cid:
                    continue
                c = cards.setdefault(cid, {"id": cid, "title": "", "state": ""})
                if data.get("problem"):
                    c["title"] = data["problem"]
                if data.get("state"):
                    c["state"] = data["state"]
    except OSError:
        return []
    return [c for c in cards.values() if c["title"] and c["state"] not in CLOSED_STATES]


def similar(title, cards=None, limit=3):
    """بطاقات مفتوحة يشبه عنوانها العنوان المكتوب (تقاطع الكلمات ÷ الأصغر ≥ نصف)؛ الأشبه أولًا."""
    a = norm_words(title)
    if len(a) < 2:
        return []
    cards = open_cards() if cards is None else cards
    out = []
    for c in cards:
        b = norm_words(c["title"])
        if not b:
            continue
        score = len(a & b) / min(len(a), len(b))
        if score >= 0.5:
            out.append(dict(id=c["id"], title=c["title"], state=c["state"], score=round(score, 2)))
    return sorted(out, key=lambda x: -x["score"])[:limit]


def payload():
    lib = criteria_lib()
    return dict(request=dict(api="request", sizes=list(SIZES), priorities=list(PRIORITIES), touches=list(TOUCHES), approvals=list(APPROVALS),
                             types=lib["types"], criteria=lib["criteria"], touch_globs={k: list(v) for k, v in TOUCH_GLOBS.items()},
                             max_files=MAX_FILES, vague=list(VAGUE)))


