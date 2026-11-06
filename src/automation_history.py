"""تاريخ الأتمتة: كلّ بطاقة من دخولها إلى نشرها أو توقّفها، مشتقٌّ من دفتر الحوكمة.

الدفتر هو المصدر ويُقرأ ولا يُكتب فيه. الجداول فهرسٌ يُعاد بناؤه في معاملة واحدة كلّما تغيّر الملف، وفيها معرّفات
وتصنيفات وأوقات وأرقام فقط (tests/test_whitelist.py). النصوص تُقرأ من الدفتر عند العرض وتُحجب منها البيانات الشخصيّة.
"""
import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

import request_page
import usage_db

PR_URL = "https://github.com/sh-school/shschool_mvp/pull/"
TEXT_MAX = 600
TERMINAL = ("published", "closed", "deferred")
STALLED_AFTER_S = 24 * 3600  # بطاقةٌ مفتوحة بلا حدثٍ يومًا كاملًا تُعدّ متوقّفة
RANKS = {"in_progress": 1, "pushed": 2, "ready_for_review": 2, "approved": 2, "verified": 2, "merged": 3, "published": 4}
STAGES = ["دخلت", "بدأ العمل", "طلب دمج", "اندمجت", "نُشرت"]
# الرحلة بين مرحلتين: عمود البداية وعمود النهاية، ومنها الوسيط لكلّ مقطع.
LEGS = [("wait", "في الطابور", "created_ts", "first_run_ts"), ("build", "الكتابة والفحص", "first_run_ts", "pr_ts"),
        ("gate", "CI والبوّابة", "pr_ts", "merged_ts"), ("deploy", "النشر", "merged_ts", "ended_ts")]
# الأسبق يغلب: «لم يُحدث النموذج شيئًا في إصلاح CI» علّتها الأولى CI الأحمر.
STOP_RULES = [
    ("preview", "رفض المعاينة", r"رفض المالك المعاينة"),
    ("conflict", "تعارض دمج", r"تعارض دمج"),
    ("ci", "CI", r"\bCI\b"),
    ("infra", "عطل بنية", r"عطل بنية|فشل بنية"),
    ("commit", "الإيداع", r"تعذّر الإيداع"),
    ("deploy", "النشر", r"النشر|فحص الصحّة"),
    ("model", "النموذج", r"فشل النموذج|لم يُحدث النموذج"),
    ("gate", "الفحص والبوّابة", r"البوّابة|prepush|مراجعة القبول|النطاق|الفشل نفسه"),
    ("owner", "قرار إداري", r"قرار المالك|أمر المالك|أرشفة|بأمر 0101"),
    ("duplicate", "مكرَّرة أو مستبدَلة", r"مكرَّرة|استُبدلت"),
]
STOP_LABELS = {k: t for k, t, _ in STOP_RULES} | {"deferred": "مؤجَّلة", "other": "أخرى"}
RUNNER_CLOSE = re.compile(r"^\[مشغّل\] أُغلقت بتقرير:\s*")
RUN_NOTE = re.compile(r"^\[مشغّل\]\s*(?:(haiku|sonnet|opus|fable)\s+)?(.+?):\s*كلفة=([\d.]+)\$\s+أدوار=(\d+)")
PR_NOTE = re.compile(r"(?:فُتح (?:الطلب|طلب الدمج)|دُفع وفُتح طلبُ الدمج|اندمج|طلبه)\s*#?(\d{3,5})|#(\d{3,5}) مدموج")
OPS = {"ci": "إصلاح CI", "review": "مراجعة القبول", "run": "تشغيل النموذج"}
KEYS = {"خلل": "bug", "ميزة صغيرة": "feature", "تحسين": "improve", "صغير": "s", "متوسط": "m", "كبير": "l",
        "مباشر": "direct", "معاينة": "preview"}
LABELS = {v: k for k, v in KEYS.items()}
HIDDEN = "•••"
OFFSITE_STATE = Path.home() / ".maestro" / "offsite_state.json"
_PARSED = {}


def ledger_path():
    return Path(request_page.LEDGER_EVENTS)


def utc(ts):
    return datetime.fromisoformat(ts).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seconds(a, b):
    return int((datetime.fromisoformat(b.replace("Z", "+00:00")) - datetime.fromisoformat(a.replace("Z", "+00:00"))).total_seconds())


def mask(text):
    return request_page.pii_pattern().sub(HIDDEN, str(text or ""))[:TEXT_MAX]


def read_events(path=None):
    """أحداث الدفتر مجمَّعةً بالبطاقة؛ سطرٌ مبتور في آخر الملف أثناء الكتابة يُتخطّى ولا يُسقط القراءة."""
    path = Path(path or ledger_path())
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    if _PARSED.get("key") != key:
        by_card = {}
        total = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                by_card.setdefault(e["id"], []).append(e)
                total += 1
        _PARSED.update(key=key, cards=by_card, total=total)
    return _PARSED["cards"], _PARSED["total"]


def stop_key(state, text):
    if state == "deferred":
        return "deferred"
    if state != "closed":
        return None
    for key, _label, rx in STOP_RULES:
        if re.search(rx, text or ""):
            return key
    return "other"


def note_op(text):
    """(العملية، النموذج، الكلفة، الأدوار) من ملاحظة تشغيل. ملخّص الإغلاق يذكر الكلفة أيضًا فلا يُعدّ مرّتين."""
    m = RUN_NOTE.match(text)
    if not m:
        return None
    label = m.group(2)
    op = "ci" if "CI" in label else "review" if "مراجعة" in label else "run"
    return op, m.group(1), float(m.group(3)), int(m.group(4))


def closing_text(events):
    """سبب الإغلاق: تقرير المشغّل إن وُجد وإلّا آخر ملاحظة."""
    notes = [e["data"].get("text", "") for e in events if e["kind"] == "note"]
    runner = [t for t in notes if RUNNER_CLOSE.match(t)]
    return RUNNER_CLOSE.sub("", runner[-1]) if runner else (notes[-1] if notes else "")


def summarize(card_id, events):
    """صفّ البطاقة وصفوف أحداثها."""
    c = dict(card_id=card_id, era="manual", source=None, req_type_key=None, size_key=None, priority=None, approval_key=None,
             state="routed", stage_rank=0, pr=None, created_ts=None, first_run_ts=None, pr_ts=None, merged_ts=None,
             ended_ts=None, last_ts=None, duration_s=None, cost_usd=0.0, runs=0, turns=0, ci_fixes=0, stop_key=None)
    rows = []
    for seq, e in enumerate(events):
        ts, kind, d = utc(e["ts"]), e["kind"], e.get("data") or {}
        row = dict(card_id=card_id, seq=seq, ts=ts, kind=kind, state=None, op=None, model=None, cost_usd=None, turns=None)
        c["last_ts"] = ts
        if kind == "created":
            c["created_ts"] = c["created_ts"] or ts
            c["source"] = re.sub(r"[^a-z_0-9]", "", str(d.get("source") or ""))[:30] or None
            c["req_type_key"] = KEYS.get(d.get("req_type"))
            c["size_key"] = KEYS.get(d.get("runner_size"))
            c["approval_key"] = KEYS.get(d.get("approval"))
            c["priority"] = d["priority"] if re.fullmatch(r"P\d", str(d.get("priority"))) else None
            if d.get("request_file"):
                c["era"] = "auto"
        elif kind == "state":
            state = d.get("state") or c["state"]
            row["state"] = c["state"] = state
            c["stage_rank"] = max(c["stage_rank"], RANKS.get(state, 0))
            if RANKS.get(state, 0) >= 1 and not c["first_run_ts"]:
                c["first_run_ts"] = ts
            if RANKS.get(state, 0) >= 2 and not c["pr_ts"]:
                c["pr_ts"] = ts
            if state == "merged":
                c["merged_ts"] = c["merged_ts"] or ts
            c["ended_ts"] = ts if state in TERMINAL else None
        elif kind == "update" and str(d.get("pr") or "").isdigit():
            c["pr"] = int(d["pr"])
            c["pr_ts"] = c["pr_ts"] or ts
            c["stage_rank"] = max(c["stage_rank"], 2)
        elif kind == "note":
            text = d.get("text", "")
            if text.startswith("[مشغّل]"):
                c["era"] = "auto"
            op = note_op(text)
            if op:
                row["op"], row["model"], row["cost_usd"], row["turns"] = op
                c["cost_usd"] += op[2]
                c["turns"] += op[3]
                c["runs"] += op[0] == "run"
                c["ci_fixes"] += op[0] == "ci"
            m = None if c["pr"] else PR_NOTE.search(text)
            if m:
                c["pr"] = int(m.group(1) or m.group(2))
        rows.append(row)
    c["cost_usd"] = round(c["cost_usd"], 4)
    if c["ended_ts"] and c["created_ts"]:
        c["duration_s"] = seconds(c["created_ts"], c["ended_ts"])
    c["stop_key"] = stop_key(c["state"], closing_text(events))
    return c, rows


def sync(con, path=None):
    """يعيد بناء الفهرس إن تغيّر الدفتر، وإلّا لا يلمس شيئًا. إعادة التشغيل لا تغيّر النتيجة."""
    path = Path(path or ledger_path())
    if not path.is_file():
        return {"synced": False, "reason": "no-ledger"}
    st = path.stat()
    done = con.execute("SELECT size, mtime_ns FROM auto_sync WHERE id=1").fetchone()
    if done and tuple(done) == (st.st_size, st.st_mtime_ns):
        return {"synced": False, "reason": "unchanged"}
    by_card, total = read_events(path)
    cards, rows = [], []
    for cid, events in by_card.items():
        c, r = summarize(cid, events)
        cards.append(c)
        rows.extend(r)
    with con:
        con.execute("DELETE FROM auto_events")
        con.execute("DELETE FROM auto_cards")
        names = list(cards[0]) if cards else []
        if cards:
            con.executemany("INSERT INTO auto_cards(%s) VALUES (%s)" % (",".join(names), ",".join(":" + n for n in names)), cards)
            names = list(rows[0])
            con.executemany("INSERT INTO auto_events(%s) VALUES (%s)" % (",".join(names), ",".join(":" + n for n in names)), rows)
        con.execute("INSERT OR REPLACE INTO auto_sync(id, size, mtime_ns, events, cards, synced_at) VALUES (1,?,?,?,?,?)",
                    (st.st_size, st.st_mtime_ns, total, len(cards), usage_db.now_iso()))
    return {"synced": True, "events": total, "cards": len(cards)}


def rows_of(con, sql, args=()):
    cur = con.execute(sql, args)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def title_of(events):
    made = next((e for e in events if e["kind"] == "created"), None)
    return mask((made or {}).get("data", {}).get("problem"))[:160]


def last_note(events):
    notes = [e["data"].get("text", "") for e in events if e["kind"] == "note"]
    return mask(notes[-1]) if notes else ""


def offsite(path=None):
    """آخر نسخة خارج الجهاز كما كتبتها أداتها؛ غيابها يُعرض ولا يُسقط الصفحة."""
    try:
        s = json.loads(Path(path or OFFSITE_STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {k: s.get(k) for k in ("ok", "ok_day", "checked_at", "files", "error")}


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def overview(con, era="all", path=None, now=None):
    """الصفحة كاملةً لنطاق واحد: all أو auto أو manual."""
    if era not in ("all", "auto", "manual"):
        era = "all"
    cards = rows_of(con, "SELECT * FROM auto_cards ORDER BY COALESCE(last_ts, created_ts) DESC")
    if era != "all":
        cards = [c for c in cards if c["era"] == era]
    ids = {c["card_id"] for c in cards}
    now = now or now_utc()
    by_card = {}
    if Path(path or ledger_path()).is_file():
        by_card = read_events(path)[0]
    stalled, stops, days = [], {}, {}
    for c in cards:
        events = by_card.get(c["card_id"], [])
        c["title"] = title_of(events)
        c["stop"] = STOP_LABELS.get(c["stop_key"])
        c["reason"] = mask(closing_text(events))[:220] if c["stop_key"] else ""
        day = (c["created_ts"] or c["last_ts"] or "")[:10]
        days.setdefault(day, dict(day=day, created=0, published=0, closed=0, cost=0.0))["created"] += 1
        end = (c["ended_ts"] or "")[:10]
        if end and c["state"] in ("published", "closed"):
            days.setdefault(end, dict(day=end, created=0, published=0, closed=0, cost=0.0))[c["state"]] += 1
        if c["stop_key"]:
            s = stops.setdefault(c["stop_key"], dict(key=c["stop_key"], label=c["stop"], n=0, cost=0.0, stages=[0] * 5))
            s["n"] += 1
            s["cost"] = round(s["cost"] + c["cost_usd"], 4)
            s["stages"][c["stage_rank"]] += 1
        if c["state"] not in TERMINAL and c["last_ts"]:
            idle = seconds(c["last_ts"], now)
            if idle >= STALLED_AFTER_S:
                stalled.append(dict(card_id=c["card_id"], title=c["title"], state=c["state"], idle_s=idle, pr=c["pr"],
                                    note=last_note(events)[:220]))
    ops = {}
    for r in rows_of(con, "SELECT card_id, ts, op, model, cost_usd, turns FROM auto_events WHERE op IS NOT NULL"):
        if r["card_id"] not in ids:
            continue
        o = ops.setdefault((r["op"], r["model"]), dict(op=OPS[r["op"]], model=r["model"] or "—", runs=0, cost=0.0, turns=0))
        o["runs"] += 1
        o["cost"] = round(o["cost"] + r["cost_usd"], 4)
        o["turns"] += r["turns"]
        day = r["ts"][:10]
        d = days.setdefault(day, dict(day=day, created=0, published=0, closed=0, cost=0.0))
        d["cost"] = round(d["cost"] + r["cost_usd"], 4)
    # مراحل الحقبة اليدويّة كُتبت دفعةً عند المزامنة فأزمنتها صفرٌ مضلِّل؛ المقاطع للمشغّل وحده.
    timed = [c for c in cards if c["era"] == "auto"]
    legs = []
    for key, label, start, end in LEGS:
        vals = [seconds(c[start], c[end]) for c in timed if c[start] and c[end] and (key != "deploy" or c["state"] == "published")]
        vals = [v for v in vals if v >= 0]
        legs.append(dict(key=key, label=label, n=len(vals), median_s=int(statistics.median(vals)) if vals else None))
    ended = [c["duration_s"] for c in cards if c["state"] == "published" and c["duration_s"] is not None]
    sync_row = rows_of(con, "SELECT events, cards, synced_at FROM auto_sync WHERE id=1")
    return dict(
        ok=True, era=era, now=now, sync=sync_row[0] if sync_row else None, pr_url=PR_URL, offsite=offsite(),
        totals=dict(cards=len(cards), published=sum(c["state"] == "published" for c in cards),
                    closed=sum(c["state"] == "closed" for c in cards), deferred=sum(c["state"] == "deferred" for c in cards),
                    active=sum(c["state"] not in TERMINAL for c in cards), stalled=len(stalled),
                    cost=round(sum(c["cost_usd"] for c in cards), 4), runs=sum(c["runs"] for c in cards),
                    ci_fixes=sum(c["ci_fixes"] for c in cards),
                    median_s=int(statistics.median(ended)) if ended else None),
        funnel=[dict(label=t, n=sum(c["stage_rank"] >= i for c in cards)) for i, t in enumerate(STAGES)],
        stages=STAGES, stops=sorted(stops.values(), key=lambda s: -s["n"]), legs=legs, stalled=sorted(stalled, key=lambda s: -s["idle_s"]),
        ops=sorted(ops.values(), key=lambda o: -o["cost"]), daily=sorted((d for d in days.values() if d["day"]), key=lambda d: d["day"]),
        cards=[{k: c[k] for k in ("card_id", "era", "title", "state", "stage_rank", "pr", "priority", "created_ts", "last_ts",
                                  "duration_s", "cost_usd", "runs", "ci_fixes", "stop", "stop_key", "reason")} for c in cards])


def card(con, card_id, path=None):
    """بطاقة واحدة بمسارها كاملًا؛ النصّ من الدفتر، والأرقام من الفهرس."""
    found = rows_of(con, "SELECT * FROM auto_cards WHERE card_id=?", (card_id,))
    if not found:
        return None
    c = found[0]
    events = []
    if Path(path or ledger_path()).is_file():
        events = read_events(path)[0].get(card_id, [])
    made = next((e["data"] for e in events if e["kind"] == "created"), {})
    timeline = []
    for r in rows_of(con, "SELECT seq, ts, kind, state, op, model, cost_usd, turns FROM auto_events WHERE card_id=? ORDER BY seq", (card_id,)):
        e = events[r["seq"]] if r["seq"] < len(events) else {"data": {}}
        d = e.get("data") or {}
        if r["kind"] == "update":
            shown = [k for k in ("pr", "merge_hold", "preview_seen", "preview_seed_failed", "preview_approved", "preview_rejected",
                                 "runner_hold", "parked") if k in d]
            if not shown:
                continue
            r["text"] = mask("، ".join("%s=%s" % (k, d[k]) for k in shown))
        elif r["kind"] == "note":
            r["text"] = mask(d.get("text"))
        elif r["kind"] == "approval":
            r["text"] = mask("اعتماد %s %s" % (d.get("by") or "", d.get("via") or ""))
        else:
            r["text"] = mask(d.get("by")) if r["kind"] == "state" else ""
        timeline.append(r)
    c.update(ok=True, title=title_of(events), impact=mask(made.get("impact")), stop=STOP_LABELS.get(c["stop_key"]),
             reason=mask(closing_text(events)) if c["stop_key"] else "", waiting=last_note(events) if c["state"] not in TERMINAL else "",
             stage_label=STAGES[c["stage_rank"]], stages=STAGES, pr_url=PR_URL + str(c["pr"]) if c["pr"] else None,
             req_type=LABELS.get(c["req_type_key"]), size=LABELS.get(c["size_key"]), approval=LABELS.get(c["approval_key"]),
             timeline=timeline)
    return c


def live(era="all"):
    """لقطة الخادم: تزامن رخيص إن تغيّر الدفتر ثمّ قراءة."""
    con = usage_db.connect()
    try:
        sync(con)
        return overview(con, era)
    finally:
        con.close()


def live_card(card_id):
    con = usage_db.connect()
    try:
        sync(con)
        return card(con, card_id)
    finally:
        con.close()


def payload():
    return dict(automation=dict(api="automation.json", card_api="automation/card.json"))
