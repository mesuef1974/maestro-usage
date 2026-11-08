"""«طلباتي»: حال كل طلب أرسلته الاستمارة، من requests/ والدفتر قراءةً فقط (بلا نموذج ولا كتابة إلا الإلغاء).

الطلب ملفّ requests/web-<طابع>.md حتى يلتقطه المشغّل فيصير ‎.done‎ (أو ‎.rejected‎)، وبطاقته في الدفتر تُعرف بعنوانها
(problem) وبأنها أُنشئت بعد وقت الإرسال. الإلغاء قبل الالتقاط فقط: نقلٌ ذرّي إلى requests/cancelled/ (المشغّل يقرأ *.md
في الجذر وحده)، فمن ينقل الملفّ أوّلًا يفوز.
"""
import json
import os
import re
from pathlib import Path

import request_page

STATE_AR = {"routed": "في الطابور", "in_progress": "يعمل الآن", "ready_for_review": "طلب الدمج مفتوح", "approved": "طلب الدمج مفتوح",
            "pushed": "طلب الدمج مفتوح", "merged": "دُمج، بانتظار النشر", "published": "نُشر", "closed": "أُغلق", "deferred": "مؤجَّل"}
NAME_RE = re.compile(r"^web-\d{8}-\d{6}(?:-\d+)?$")
COST_RE = re.compile(r"كلفة=([0-9.]+)\$")


def parse_request(text):
    """حقول ملفّ الطلب: سطرٌ لكل مفتاح (المفتاح قبل أول «:»)."""
    out = {}
    for ln in text.splitlines():
        k, sep, v = ln.partition(":")
        if sep:
            out[k.strip()] = v.strip()
    return out


def failed_checks(text):
    """الفحوص الفاشلة (✘) من سجلّ، كلٌّ حتى 160 حرفًا."""
    return [f.strip() for f in re.findall(r"✘\s*([^✔✘]{1,160})", " ".join(str(text).split()))]


def short_report(text, fails=(), limit=300):
    """تقرير الإغلاق مختصرًا: الحكم قبل «آخر سبب»، ثم الفحوص الفاشلة وحدها بدل ذيل السجلّ المقصوص.

    fails من ملاحظة «آخر سجلّ فشل» إن وُجدت (التقرير نفسه مقصوص فقد لا يبلغ سطر ✘)."""
    text = " ".join(str(text).split())
    head, sep, tail = text.partition("آخر سبب:")
    fails = list(fails) or failed_checks(tail)
    if sep:
        text = head.rstrip(" ؛;") + ("؛ الفاشل: " + " | ".join(fails) if fails else "")
    return text[:limit]


def _cards(path=None):
    """بطاقات الدفتر بحقولها المجمّعة، والكلفة من ملاحظات المشغّل، وتقرير الإغلاق."""
    path = Path(path or request_page.LEDGER_EVENTS)
    cards = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                cid, d = e.get("id"), e.get("data") or {}
                if not cid:
                    continue
                c = cards.setdefault(cid, {"id": cid, "created": "", "cost": 0.0, "report": "", "state": "", "hold": False})
                if e.get("kind") == "created":
                    c["created"], c["title"] = str(e.get("ts") or ""), d.get("problem", "")
                if d.get("state"):
                    c["state"], c["state_ts"] = d["state"], str(e.get("ts") or "")
                if "pr" in d and d["pr"]:
                    c["pr"] = d["pr"]
                if "runner_hold" in d:
                    c["hold"] = bool(d["runner_hold"])
                text = str(d.get("text") or "")
                if e.get("kind") == "note" and text.startswith("[مشغّل]"):
                    if " تشغيل " in text or "مراجعة القبول" in text:
                        m = COST_RE.search(text)
                        c["cost"] += float(m.group(1)) if m else 0.0
                    if text.startswith("[مشغّل] أُغلقت بتقرير:"):
                        c["report_raw"] = text[len("[مشغّل] أُغلقت بتقرير:"):]
                    if text.startswith("[مشغّل] آخر سجلّ فشل:"):
                        c["fails"] = failed_checks(text)
    except OSError:
        pass
    for c in cards.values():
        if "report_raw" in c:
            c["report"] = short_report(c.pop("report_raw"), c.get("fails", ()))
    return cards


def _match(fields, submitted, cards):
    """البطاقة التي أنشأها المشغّل من هذا الطلب: العنوان نفسه، وأُنشئت بعد الإرسال، الأقرب زمنًا."""
    title = fields.get("العنوان", "")
    cands = [c for c in cards.values() if c.get("title") == title and c["created"][:19].replace("T", " ") >= submitted.replace("T", " ")]
    return min(cands, key=lambda c: c["created"]) if cands else None


def status_of(kind, card):
    if kind == "pending":
        return "pending", "في الانتظار: يلتقطه المشغّل خلال 5 دقائق"
    if kind == "cancelled":
        return "cancelled", "أُلغي"
    if kind == "rejected":
        return "rejected", "رُفض عند الالتقاط (حقل ناقص أو حجم مجهول)"
    if not card:
        return "picked", "التُقط، والبطاقة لم تظهر في الدفتر بعد"
    st = card.get("state", "")
    if st == "closed" and card.get("report"):
        return "failed", "أُغلق بتقرير: " + card["report"]
    if card.get("hold") and st not in ("published", "merged", "closed"):
        return "held", "بانتظار قرارك في طابور المالك"
    label = STATE_AR.get(st, st or "؟")
    if card.get("pr") and st in ("ready_for_review", "approved", "pushed", "in_progress"):
        label += " (#%s)" % card["pr"]
    return st or "picked", label


def list_requests(limit=20, ledger=None):
    """أحدث الطلبات أولًا: الرقم، والعنوان، والوقت، والحال، والبطاقة، والكلفة، وإمكان الإلغاء وإعادة المحاولة."""
    d = request_page.requests_dir()
    items = []
    for kind, pattern in (("pending", "web-*.md"), ("done", "web-*.done"), ("rejected", "web-*.rejected"), ("cancelled", "cancelled/web-*.md")):
        for f in d.glob(pattern):
            if not NAME_RE.match(f.name.split(".")[0]):
                continue
            try:
                fields = parse_request(f.read_text(encoding="utf-8"))
            except OSError:
                continue
            items.append((kind, f, fields))
    items.sort(key=lambda x: x[1].name.split(".")[0], reverse=True)
    cards = _cards(ledger) if any(k == "done" for k, _f, _x in items[:limit]) else {}
    out = []
    for kind, f, fields in items[:limit]:
        submitted = fields.get("مقدَّم في", "")
        card = _match(fields, submitted, cards) if kind == "done" else None
        code, label = status_of(kind, card)
        out.append(dict(name=f.name.split(".")[0], title=fields.get("العنوان", ""), submitted=submitted, type=fields.get("النوع", ""),
                        size=fields.get("الوسم", ""), status=code, label=label, card=card["id"] if card else "",
                        pr=card.get("pr") if card else None, cost=round(card["cost"], 3) if card else 0.0,
                        attachments=bool(fields.get("المرفقات")), can_cancel=kind == "pending", can_retry=code in ("failed", "rejected", "cancelled")))
    return out


def cancel(name):
    """يلغي طلبًا لم يُلتقط بعد: نقلٌ ذرّي إلى requests/cancelled/؛ ValueError إن كان الاسم غير صالح أو التُقط."""
    if not NAME_RE.match(str(name or "")):
        raise ValueError("اسم طلب غير صالح")
    d = request_page.requests_dir()
    src = d / (name + ".md")
    (d / "cancelled").mkdir(exist_ok=True)
    try:
        os.replace(src, d / "cancelled" / (name + ".md"))
    except FileNotFoundError:
        raise ValueError("لا يمكن الإلغاء: التقطه المشغّل أو أُلغي من قبل") from None
    return {"ok": True, "name": name}


TYPE_ALIASES = {"إصلاح عيب": "خلل", "عيب": "خلل", "ميزة": "ميزة صغيرة", "ميزة جديدة": "ميزة صغيرة", "واجهة": "تحسين واجهة"}


def _known_type(t):
    """نوعٌ خارج القائمة (كُتب بيدٍ أو بأداة) يُطابَق بمرادفه فلا ترفض الاستمارةُ إعادةَ المحاولة بـ«اختر نوع الطلب»."""
    t = (t or "").strip()
    return t if t in request_page.TYPES else TYPE_ALIASES.get(t, "")


def retry_fields(name, ledger=None):
    """حقول الطلب الأصلي للاستمارة مع سبب الفشل السابق، لإعادة المحاولة بطلبٍ أقوى لا بالصياغة نفسها."""
    if not NAME_RE.match(str(name or "")):
        raise ValueError("اسم طلب غير صالح")
    d = request_page.requests_dir()
    for p in (d / (name + ".done"), d / (name + ".rejected"), d / "cancelled" / (name + ".md"), d / (name + ".md")):
        if p.is_file():
            f = parse_request(p.read_text(encoding="utf-8"))
            break
    else:
        raise ValueError("الطلب غير موجود")
    card = _match(f, f.get("مقدَّم في", ""), _cards(ledger)) if p.suffix == ".done" else None
    ids = [int(x) for x in re.split(r"[،,\s]+", f.get("معايير مرقّمة", "")) if x.isdigit()]
    lib = request_page.criteria_lib()["by_id"]
    by_text = {v["text"]: i for i, v in lib.items()}
    for a in (x.strip() for x in f.get("معايير القبول", "").split("؛")):  # طلبٌ كُتب بلا أرقام: يُستردّ رقمُ كلّ معيارٍ نصُّه من القائمة
        if a in by_text and by_text[a] not in ids:
            ids.append(by_text[a])
    ids = ids or [1, 3]  # prepush ونطاق: لا بدّ من فحصٍ آليّ واحدٍ على الأقل فلا ترفض الاستمارةُ الإعادة
    texts = {lib[i]["text"] for i in ids if i in lib}
    extra = [a.strip() for a in f.get("معايير القبول", "").split("؛") if a.strip() and a.strip() not in texts]
    ask = f.get("المطلوب", "").replace(" / ", "\n")
    if card and card.get("report"):
        tail = "\nما أضفته هذه المرة لتجنّبه: "
        head = "\nسبب فشل المحاولة السابقة (%s): " % card["id"]
        room = request_page.MAX["ask"] - len(ask) - len(head) - len(tail)  # لا يتجاوز سقف الحقل فترفضه الاستمارة
        if room > 40:
            ask += head + card["report"][:room] + tail
    return dict(title=f.get("العنوان", ""), ask=ask, type=_known_type(f.get("النوع", "")), criteria=ids, accept="\n".join(extra),
                size=f.get("الوسم", "") if f.get("الوسم") in request_page.SIZES else "", priority=f.get("الأولوية", ""),
                approval=f.get("الاعتماد", ""), page=f.get("الصفحة", ""), out_of_scope=f.get("خارج النطاق", ""),
                files=[x.strip() for x in f.get("الملفات", "").split("،") if x.strip()], retry_of=name, card=card["id"] if card else "")
