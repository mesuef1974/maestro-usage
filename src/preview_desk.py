"""مكتب المعاينة في ميزان: البطاقات التي تنتظر المالك، وما يعرضه 8500، وقراره بزرّ بدل سطر الأوامر.

القراءة من الدفتر و/health/ لخادم المعاينة. والقرار يمرّ بـ runner.py --approve/--reject نفسه،
فهو الذي يربطه بالرأس المعروض ويكتبه في الدفتر؛ هذا الملف لا يكتب في الدفتر مباشرة.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import automation_history as ah  # noqa: E402
import my_requests  # noqa: E402
import request_page  # noqa: E402

ROOT = Path.home() / "delivery_manager_work"
HEALTH_URL = "http://localhost:8500/health/"
CARD_ID = re.compile(r"W-[0-9]{8}-[0-9]{3}")
RETRY_LINE = re.compile(r"^إعادة لـ: (\S+)", re.M)
PR_URL = ah.PR_URL
MAX_REASON = 300
NEEDS_SINCE = "2026-11-07"  # ما قبله قُضي فيه، فلا يُعرض 26 إغلاقًا قديمًا


def served_commit(url=HEALTH_URL):
    """الرأس الذي يخدمه 8500 الآن؛ فراغٌ إن كان متوقّفًا."""
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return str(json.loads(r.read().decode("utf-8")).get("commit") or "")
    except (OSError, ValueError):
        return ""


def fold(events):
    """حالة البطاقة وحقول المعاينة من أحداثها."""
    c = {"state": "", "approval": "", "resume": None, "seen": "", "info": None, "approved": False, "rejected": "", "visual": []}
    for e in events:
        d = e.get("data") or {}
        if e.get("kind") == "created":
            c["approval"] = d.get("approval") or ""
        elif e.get("kind") == "state":
            c["state"] = d.get("state") or c["state"]
        elif e.get("kind") == "update":
            for src, dst in (("runner_resume", "resume"), ("preview_seen", "seen"), ("preview_info", "info"),
                             ("preview_approved", "approved"), ("preview_rejected", "rejected"), ("visual_pages", "visual")):
                if src in d:
                    c[dst] = d[src]
    return c


def waiting(path=None, served=None):
    """بطاقات المعاينة التي لم يُقضَ فيها، والجاهزة منها ما يخدمه 8500 أو خانتها فعلًا."""
    path = Path(path or ah.ledger_path())
    if not path.is_file():
        return []
    served = served_commit() if served is None else served
    out = []
    for cid, events in ah.read_events(path)[0].items():
        c = fold(events)
        head = (c["resume"] or {}).get("head", "")
        if c["approval"] != "معاينة" or c["state"] in ah.TERMINAL or not head or c["approved"] or c["rejected"]:
            continue
        info = c["info"] or {}
        url = info.get("url", "")
        slot = re.match(r"http://localhost:(86[0-9]{2})/", url)
        now_served = served_commit("http://localhost:%s/health/" % slot[1]) if slot else served
        ready = c["seen"] == head and bool(now_served) and head.startswith(now_served)
        pr = (c["resume"] or {}).get("pr")
        out.append(dict(card_id=cid, title=ah.title_of(events), head=head[:8], ready=ready, pr=pr,
                        pr_url=(PR_URL + str(pr)) if pr else "", url=info.get("url", ""), account=info.get("account", ""),
                        role=info.get("role", ""), checks=[ah.mask(x) for x in info.get("checks") or []], visual=c["visual"] or []))
    return sorted(out, key=lambda x: (not x["ready"], x["card_id"]))


def pending_retries(folder=None):
    """طلبات إعادة لم يلتقطها المشغّل بعد: بلا هذا تبقى البطاقة بزرّها دقائق فتتكرّر الإعادة (W-011 وW-012)."""
    folder = Path(folder or ROOT / "requests")
    found = (RETRY_LINE.search(f.read_text(encoding="utf-8")) for f in folder.glob("*.md"))
    return {m[1] for m in found if m}


def needs_decision(path=None, pending=None):
    """بطاقاتٌ أغلقها المشغّل بعد فشلها ولم يُعَد طلبها ولم يقرّ المالك إغلاقها: تبقى ظاهرة حتى قراره."""
    path = Path(path or ah.ledger_path())
    if not path.is_file():
        return []
    by_card = ah.read_events(path)[0]
    made = {cid: next((e.get("data") or {} for e in ev if e.get("kind") == "created"), {}) for cid, ev in by_card.items()}
    retried = {d.get("retry_of") for d in made.values() if d.get("retry_of")} | (pending_retries() if pending is None else pending)
    out = []
    for cid, events in by_card.items():
        d = made[cid]
        if cid[2:10] < NEEDS_SINCE.replace("-", "") or fold(events)["state"] != "closed" or d.get("request_file") in retried or not d.get("request_file"):
            continue
        if any(e.get("kind") == "update" and (e.get("data") or {}).get("owner_dismissed") for e in events):
            continue
        reason = ah.closing_text(events)
        if not reason:
            continue
        notes = [(e.get("data") or {}).get("text", "") for e in events if e.get("kind") == "note"]
        cost = sum(float(m[3]) for m in map(ah.RUN_NOTE.match, notes) if m)
        out.append(dict(card_id=cid, title=ah.title_of(events), reason=ah.mask(reason)[:300], cost=round(cost, 2)))
    return sorted(out, key=lambda x: x["card_id"])


def payload(path=None):
    served = served_commit()
    return dict(ok=True, up=bool(served), served=served, cards=waiting(path, served), needs=needs_decision(path))


def _need(params, needs=None):
    cid = str(params.get("card") or "")
    if not CARD_ID.fullmatch(cid) or cid not in {c["card_id"] for c in (needs_decision() if needs is None else needs)}:
        raise request_page.ValidationError("البطاقة لا تنتظر قرارًا", "card")
    return cid


def retry(params, needs=None, path=None):
    """إعادة بزرّ: الطلب الأصلي نفسه مع سبب الفشل، ويلتقطه المشغّل في دورته."""
    cid = _need(params, needs)
    made = next(e.get("data") or {} for e in ah.read_events(Path(path or ah.ledger_path()))[0][cid] if e.get("kind") == "created")
    fields = my_requests.retry_fields(made["request_file"])
    fields.pop("card", None)
    return request_page.submit(fields)


def dismiss(params, run=subprocess.run, needs=None):
    cid = _need(params, needs)
    p = run([sys.executable, str(ROOT / "tools" / "runner.py"), "--dismiss", cid], cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60)
    if p.returncode:
        raise request_page.ValidationError((p.stderr or "تعذّر التسجيل").strip()[-200:], "")
    return dict(ok=True, message=(p.stdout or "").strip()[-200:])


def password(_params=None, env=None):
    """كلمة حسابات المعاينة المحلية للنسخ؛ لا تُضمَّن في الصفحة."""
    env = Path(env or ROOT / "tools" / ".preview_accounts.env")
    for line in env.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "PREVIEW_ACCOUNTS_PASSWORD":
            return dict(ok=True, password=value.strip())
    raise request_page.ValidationError("كلمة المعاينة غير موجودة", "")


def decide(params, run=subprocess.run, cards=None):
    """اعتماد أو رفض من الزرّ: البطاقة منتظرة، والاعتماد لما يُعرض الآن، والرفض بسبب."""
    cid = str(params.get("card") or "")
    approve = params.get("approve") is True
    reason = " ".join(str(params.get("reason") or "").split())[:MAX_REASON]
    if not CARD_ID.fullmatch(cid):
        raise request_page.ValidationError("معرّف بطاقة غير صالح", "card")
    card = next((c for c in (waiting() if cards is None else cards) if c["card_id"] == cid), None)
    if card is None:
        raise request_page.ValidationError("البطاقة لا تنتظر معاينة", "card")
    if approve and not card["ready"]:
        raise request_page.ValidationError("هذه البطاقة غير معروضة الآن", "card")
    if not approve and not reason:
        raise request_page.ValidationError("الرفض يحتاج سببًا", "reason")
    cmd = [sys.executable, str(ROOT / "tools" / "runner.py")] + (["--approve", cid] if approve else ["--reject", cid, "--reason", reason])
    p = run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    text = (p.stdout or p.stderr or "").strip()[-300:]
    if p.returncode:
        raise request_page.ValidationError(text or "تعذّر تسجيل القرار", "")
    return dict(ok=True, message=text)
