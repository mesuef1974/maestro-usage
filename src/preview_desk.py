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
import request_page  # noqa: E402

ROOT = Path.home() / "delivery_manager_work"
HEALTH_URL = "http://localhost:8500/health/"
CARD_ID = re.compile(r"W-[0-9]{8}-[0-9]{3}")
PR_URL = ah.PR_URL
MAX_REASON = 300


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
    """بطاقات المعاينة التي لم يُقضَ فيها، والجاهزة منها ما يخدمه 8500 فعلًا."""
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
        ready = c["seen"] == head and bool(served) and head.startswith(served)
        pr = (c["resume"] or {}).get("pr")
        out.append(dict(card_id=cid, title=ah.title_of(events), head=head[:8], ready=ready, pr=pr,
                        pr_url=(PR_URL + str(pr)) if pr else "", url=info.get("url", ""), account=info.get("account", ""),
                        role=info.get("role", ""), checks=[ah.mask(x) for x in info.get("checks") or []], visual=c["visual"] or []))
    return sorted(out, key=lambda x: (not x["ready"], x["card_id"]))


def payload(path=None):
    served = served_commit()
    return dict(ok=True, up=bool(served), served=served, cards=waiting(path, served))


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
        raise request_page.ValidationError("هذه البطاقة ليست المعروضة على 8500 الآن", "card")
    if not approve and not reason:
        raise request_page.ValidationError("الرفض يحتاج سببًا", "reason")
    cmd = [sys.executable, str(ROOT / "tools" / "runner.py")] + (["--approve", cid] if approve else ["--reject", cid, "--reason", reason])
    p = run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    text = (p.stdout or p.stderr or "").strip()[-300:]
    if p.returncode:
        raise request_page.ValidationError(text or "تعذّر تسجيل القرار", "")
    return dict(ok=True, message=text)
