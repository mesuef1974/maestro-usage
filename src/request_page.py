"""صفحة «طلب جديد» (D-519م/D-521م): بديل محادثة المالك — تكتب ملفّاً في requests/ بقالب الاستلام نفسه، بصفر توكنز.

POST /request في serve.py ينادي submit(): يتحقّق من الحقول ويكتب requests/<طابع>-<رقم>.md؛ ولا يتصل بنموذج ولا بالدفتر
(الاستلام في delivery_manager_work/tools/runner.py يحوّل الملفّ بطاقةً في دورته التالية).
"""
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
MAX = {"title": 120, "ask": 1500, "accept": 1500}
DEFAULT_DIR = Path.home() / "delivery_manager_work" / "requests"


def requests_dir():
    return Path(os.environ.get("RUNNER_REQUESTS") or DEFAULT_DIR)


def _clean(v, limit):
    return re.sub(r"[\r\n]+", " ", str(v or "")).strip()[:limit]


def validate(params):
    """يعيد (حقول نظيفة، خطأ|None)؛ خطأٌ واحد بالعربية يسمّي الحقل."""
    title, ask = _clean(params.get("title"), MAX["title"]), _clean(params.get("ask"), MAX["ask"])
    raw = params.get("accept") or []
    lines = [_clean(x, MAX["accept"]) for x in (raw.splitlines() if isinstance(raw, str) else raw)]
    lines = [x for x in lines if x]
    size, prio = str(params.get("size") or ""), str(params.get("priority") or "P2")
    touches = [t for t in (params.get("touches") or []) if t in TOUCHES]
    for name, ok in (("العنوان", title), ("المطلوب", ask), ("معايير القبول", lines)):
        if not ok:
            return None, "الحقل ناقص: " + name
    if size not in SIZES:
        return None, "الوسم غير صالح"
    if prio not in PRIORITIES:
        return None, "الأولوية غير صالحة"
    return dict(title=title, ask=ask, accept=" ؛ ".join(lines), size=size, priority=prio, touches=touches), None


def submit(params, now=None):
    """يكتب الطلب ويعيد {ok, file}؛ ValueError برسالة الحقل الناقص عند الرفض."""
    fields, err = validate(params)
    if err:
        raise ValueError(err)
    d = requests_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", now or time.localtime())
    path = d / ("web-%s.md" % stamp)
    n = 1
    while path.exists():
        n += 1
        path = d / ("web-%s-%d.md" % (stamp, n))
    body = "العنوان: %s\nالمطلوب: %s\nمعايير القبول: %s\nالوسم: %s\nالأولوية: %s\n" % (
        fields["title"], fields["ask"], fields["accept"], fields["size"], fields["priority"])
    if fields["touches"]:
        body += "يمسّ: %s\n" % "، ".join(fields["touches"])
    path.write_text(body, encoding="utf-8")
    return dict(ok=True, file=path.name)


def payload():
    return dict(request=dict(api="request", sizes=list(SIZES), priorities=list(PRIORITIES), touches=list(TOUCHES)))


def render(data, stamp, page="request.html"):
    return ui.render(page, data, {"__STAMP__": stamp})


def write(path, data, stamp, page="request.html"):
    ui.write(path, render(data, stamp, page))
