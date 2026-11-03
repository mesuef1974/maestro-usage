"""حجم بيانات كلود المحلية (‎~/.claude): مسح رقمي بحسب المجلد الأعلى والمشروع والامتداد والعمر، لقطات في القاعدة لمنحنى النمو،
وأدوات تحرير مساحة آمنة: نقل إلى حجر (‎~/.maestro/quarantine/<ts>_<مجموعة>) بقائمة ملفات، استرجاع، وإفراغ نهائي بأمر صريح.

لا أسماء ملفات في القاعدة ولا الصفحة: مجلدات وامتدادات وأعداد وأحجام وأزمنة فقط؛ القائمة التفصيلية في manifest.json داخل مجلد الحجر.
الأمان: لا يُنقل إلا ما يقع تحت ‎~/.claude وضمن المجموعات المعرَّفة، ولا ملف لُمس خلال 24 ساعة، ولا سجل جلسة لم يُحمَّل كاملًا إلى القاعدة.
المجلدات التي ليست من Claude Code (مستودع git، مشاريع المالك…) تُعرض للمعرفة فقط ولا تمسّها أي أداة.
"""
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.expanduser("~"), ".claude")
QUARANTINE = os.path.join(os.path.expanduser("~"), ".maestro", "quarantine")
SCAN_INTERVAL_SEC = 3600  # مسح كامل كل ساعة داخل الدورة (المسح نحو 80 ألف ملف ويستغرق ثوانيَ)
MIN_AGE_SEC = 86400  # لا يُنقل ملف لُمس خلال آخر 24 ساعة (قد يكون مفتوحًا لجلسة حيّة)
EXT_LIMIT = 12
ROOT_KEY = "(root)"

# المجلد الأعلى ← نوعه. ما ليس هنا «foreign»: ليس من Claude Code (مستودع git، مشاريع المالك…) ولا تمسّه الأدوات.
KIND_OF = {
    "projects": "transcripts", "file-history": "file_history", "shell-snapshots": "shell_snapshots", "plugins": "plugins",
    "skills": "skills", "skills_archive": "skills", "templates": "skills", "patterns": "skills", "commands": "skills", "hooks": "skills",
    "agents": "skills", "improve_claude": "memory", "backups": "backups", "logs": "logs", "telemetry": "logs", "cache": "logs", "debug": "logs",
    "statsig": "logs", "scheduled-tasks": "config", "sessions": "config", "state": "config", "daemon": "config", "handoff": "config",
    "chrome": "config", "ide": "config", "todos": "config", ROOT_KEY: "config",
}
# (المفتاح، الاسم، ما هو، لماذا يكبر، هل حذفه آمن)
KINDS = [
    ("transcripts", "سجلات الجلسات", "ملفات jsonl في projects: كل رسالة وردّ ومخرجات الأدوات لكل جلسة ووكيل فرعي.",
     "كل جلسة تضيف ميغابايتات؛ الجلسات الطويلة والوكلاء الفرعيون ومخرجات الأدوات الكبيرة تضخّمها.",
     "نعم بعد تحميلها إلى القاعدة هنا؛ تفقد فقط إمكانية استئناف الجلسة القديمة (claude --resume)."),
    ("file_history", "تاريخ الملفات", "نسخ الملفات قبل كل تعديل تجريه الأداة (للتراجع داخل الجلسة).", "كل تعديل يحفظ نسخة كاملة.",
     "نعم للقديم منها؛ لا تحتاجها خارج الجلسة التي أنشأتها."),
    ("shell_snapshots", "لقطات الصدفة", "لقطة بيئة الصدفة عند بدء كل جلسة.", "ملف لكل جلسة.", "نعم للقديم منها."),
    ("plugins", "الإضافات", "ما ثُبّت من إضافات وتبعياتها.", "التثبيت والتحديث.", "لا من هنا؛ أزل الإضافة من Claude Code."),
    ("skills", "المهارات والقوالب", "المهارات والأوامر والقوالب والأنماط والخطافات.", "ما تضيفه بيدك.", "لا؛ هذه إعداداتك."),
    ("memory", "الذاكرة", "ذاكرة التحسين والتوجيه.", "ما يُحفظ من تعلّم.", "لا؛ إعدادات."),
    ("backups", "نسخ احتياطية", "نسخ احتياطية داخلية.", "تتراكم مع الوقت.", "يدويًّا بحذر."),
    ("logs", "سجلات وذاكرة مؤقتة", "logs وtelemetry وcache وdebug.", "تشغيل يومي.", "غالبًا نعم؛ صغيرة."),
    ("config", "إعدادات وحالة", "settings وملفات الجذر والمهام المجدولة والحالة.", "لا يكبر.", "لا."),
    ("foreign", "ليست من Claude Code", "مجلدات وُضعت داخل ‎~/.claude وليست من الأداة (مستودع git، مشاريع، node_modules…).",
     "بحسب ما يُوضع فيها.", "خارج نطاق هذه الأدوات؛ راجعها بنفسك."),
]
KIND_LABEL = {k[0]: k[1] for k in KINDS}
AGE_BUCKETS = (("b7", 7), ("b30", 30), ("b90", 90), ("b90p", None))  # ≤7 و≤30 و≤90 و>90 يومًا

# مجموعات التحرير: (المفتاح، الاسم، الوصف، الأيام الافتراضية، خيارات الأيام)
GROUPS = [
    ("orphan_projects", "سجلات مشاريع اختفت مجلداتها",
     "مشاريع في projects لم يعد مجلد عملها موجودًا على القرص (مثل worktrees حُذفت)؛ كل ملفاتها الأقدم من يوم.", 0, [0]),
    ("old_transcripts", "سجلات جلسات قديمة",
     "ملفات jsonl أقدم من المدة المختارة وحُمّلت كاملةً إلى القاعدة هنا (الأرقام والتقارير لا تتأثر).", 90, [30, 60, 90, 180]),
    ("file_history", "تاريخ الملفات القديم", "نسخ ما قبل التعديل الأقدم من المدة المختارة.", 30, [7, 30, 90]),
    ("shell_snapshots", "لقطات الصدفة القديمة", "لقطات بيئة الصدفة الأقدم من المدة المختارة.", 7, [7, 30]),
]
GROUP_KEYS = {g[0] for g in GROUPS}


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _agg():
    return {"bytes": 0, "files": 0, "newest": 0.0, "oldest": 0.0, "b7": 0, "b30": 0, "b90": 0, "b90p": 0}


def _add(a, size, mtime, now):
    a["bytes"] += size
    a["files"] += 1
    a["newest"] = max(a["newest"], mtime)
    a["oldest"] = mtime if not a["oldest"] else min(a["oldest"], mtime)
    days = (now - mtime) / 86400
    for key, lim in AGE_BUCKETS:
        if lim is None or days <= lim:
            a[key] += size
            break


def _rel_parts(root, dirpath):
    rel = os.path.relpath(dirpath, root)
    return [] if rel == "." else rel.replace("\\", "/").split("/")


def scan(root=ROOT, now=None):
    """يمشي الشجرة مرة واحدة (بلا وصلات رمزية) ويجمّع أرقامًا فقط."""
    now = now or time.time()
    t0 = time.time()
    top, proj, ext, total = {}, {}, {}, _agg()
    for dirpath, dirnames, filenames in os.walk(root):
        parts = _rel_parts(root, dirpath)
        t = parts[0] if parts else ROOT_KEY
        for f in filenames:
            try:
                st = os.stat(os.path.join(dirpath, f))
            except OSError:
                continue
            size, mt = st.st_size, st.st_mtime
            _add(total, size, mt, now)
            _add(top.setdefault(t, _agg()), size, mt, now)
            e = os.path.splitext(f)[1].lower() or "(بلا)"
            _add(ext.setdefault(e, _agg()), size, mt, now)
            if t == "projects" and len(parts) > 1:
                p = proj.setdefault(parts[1], _agg())
                _add(p, size, mt, now)
                if e == ".jsonl":
                    p["jsonl"] = p.get("jsonl", 0) + 1
                if "subagents" in parts[2:]:
                    p["sub"] = p.get("sub", 0) + size
    return {"ts": _iso(now), "seconds": round(time.time() - t0, 1), "total": total, "top": top, "proj": proj,
            "ext": dict(sorted(ext.items(), key=lambda kv: -kv[1]["bytes"])[:EXT_LIMIT])}


def persist(con, s):
    rows = []
    for kind, table in (("top", s["top"]), ("proj", s["proj"]), ("ext", s["ext"])):
        for name, a in table.items():
            rows.append((s["ts"], kind, name, a["bytes"], a["files"], _iso(a["newest"]) if a["newest"] else None,
                         _iso(a["oldest"]) if a["oldest"] else None, a["b7"], a["b30"], a["b90"], a["b90p"], a.get("jsonl", 0), a.get("sub", 0)))
    con.execute("INSERT OR REPLACE INTO storage_scans(ts, total_bytes, files, seconds) VALUES (?,?,?,?)",
                (s["ts"], s["total"]["bytes"], s["total"]["files"], s["seconds"]))
    con.executemany("INSERT OR REPLACE INTO storage_dirs(ts, kind, name, bytes, files, newest, oldest, b7, b30, b90, b90p, jsonl, sub) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()


def last_scan_ts(con):
    return con.execute("SELECT MAX(ts) FROM storage_scans").fetchone()[0]


def due(con, now=None):
    last = last_scan_ts(con)
    if not last:
        return True
    last_t = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    return (now or time.time()) - last_t >= SCAN_INTERVAL_SEC - 30


def run(con, root=ROOT, now=None, force=False):
    """داخل الدورة: مسح كل ساعة (أو بطلب)؛ يعيد ملخّصًا رقميًّا."""
    if not force and not due(con, now):
        return {"scanned": 0}
    s = scan(root, now)
    persist(con, s)
    return {"scanned": 1, "seconds": s["seconds"], "bytes": s["total"]["bytes"], "files": s["total"]["files"]}


# ---------- ربط المشاريع بالقاعدة ----------
def _proj_of(source_path):
    return source_path.replace("\\", "/").split("/", 1)[0]


def project_facts(con):
    """لكل مجلد مشروع: هل ما زال مجلد عمله على القرص (من sessions.cwd) ونسبة ما حُمّل من سجلاته (ingest_state)."""
    facts = {}
    for sp, off, size, cwd in con.execute(
            "SELECT i.source_path, i.offset_bytes, i.size_bytes, s.cwd FROM ingest_state i LEFT JOIN sessions s ON s.session_key=i.session_key"):
        f = facts.setdefault(_proj_of(sp), {"off": 0, "size": 0, "cwds": set()})
        f["off"] += off or 0
        f["size"] += size or 0
        if cwd:
            f["cwds"].add(cwd)
    out = {}
    for p, f in facts.items():
        known = [c for c in f["cwds"]]
        out[p] = {"ingested": (f["off"] / f["size"]) if f["size"] else None,
                  "exists": (any(os.path.isdir(c) for c in known) if known else None)}
    return out


def ingested_files(con):
    """المسارات (نسبةً إلى projects، بشرطة مائلة) التي حُمّلت كاملةً: offset ≥ size."""
    return {sp.replace("\\", "/") for sp, off, size in con.execute("SELECT source_path, offset_bytes, size_bytes FROM ingest_state")
            if size and off >= size}


# ---------- التحرير الآمن ----------
def _inside(path, base):
    rp, rb = os.path.realpath(path), os.path.realpath(base)
    return rp == rb or rp.startswith(rb.rstrip("\\/") + os.sep)


def _walk_files(base):
    for dirpath, dirnames, filenames in os.walk(base):
        for f in filenames:
            p = os.path.join(dirpath, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            yield p, st.st_size, st.st_mtime


def candidates(group, days, root=ROOT, con=None, now=None):
    """الملفات المرشّحة للنقل (مسار مطلق، حجم، mtime) بحسب المجموعة؛ الصفحة لا ترى المسارات، فقط مجاميعها."""
    if group not in GROUP_KEYS:
        raise ValueError("مجموعة غير معروفة")
    now = now or time.time()
    days = max(0, int(days or 0))
    cutoff = min(now - MIN_AGE_SEC, now - days * 86400)
    out = []
    if group == "orphan_projects":
        facts = project_facts(con) if con is not None else {}
        pdir = os.path.join(root, "projects")
        if os.path.isdir(pdir):
            for name in os.listdir(pdir):
                f = facts.get(name)
                if not f or f["exists"] is not False:  # مجهول الحال لا يُنقل
                    continue
                out += [c for c in _walk_files(os.path.join(pdir, name)) if c[2] <= cutoff]
    elif group == "old_transcripts":
        done = ingested_files(con) if con is not None else set()
        pdir = os.path.join(root, "projects")
        for p, size, mt in _walk_files(pdir) if os.path.isdir(pdir) else ():
            if mt > cutoff or not p.lower().endswith(".jsonl"):
                continue
            if os.path.relpath(p, pdir).replace("\\", "/") in done:
                out.append((p, size, mt))
    elif group == "file_history":
        base = os.path.join(root, "file-history")
        out = [c for c in (_walk_files(base) if os.path.isdir(base) else ()) if c[2] <= cutoff]
    elif group == "shell_snapshots":
        base = os.path.join(root, "shell-snapshots")
        cutoff = min(cutoff, now - 7 * 86400)
        out = [c for c in (_walk_files(base) if os.path.isdir(base) else ()) if c[2] <= cutoff]
    return [c for c in out if _inside(c[0], root)]


def plan(group, days, root=ROOT, con=None, now=None):
    """معاينة بلا تغيير: الأعداد والأحجام مجمّعة بحسب المجلد الفرعي الأول (مشروع أو مجلد)."""
    cands = candidates(group, days, root, con, now)
    by = {}
    for p, size, _mt in cands:
        parts = _rel_parts(root, os.path.dirname(p)) or [ROOT_KEY]
        key = parts[1] if parts[0] == "projects" and len(parts) > 1 else parts[0]
        b = by.setdefault(key, {"name": key, "files": 0, "bytes": 0})
        b["files"] += 1
        b["bytes"] += size
    return {"group": group, "days": days, "files": len(cands), "bytes": sum(c[1] for c in cands),
            "by": sorted(by.values(), key=lambda b: -b["bytes"])[:40]}


def apply(group, days, con, root=ROOT, quarantine=QUARANTINE, now=None):
    """ينقل المرشّحين إلى مجلد حجر جديد مع manifest.json ويسجّل العملية في storage_actions."""
    now = now or time.time()
    cands = candidates(group, days, root, con, now)
    if not cands:
        return {"ok": True, "files": 0, "bytes": 0, "id": None}
    ts = _iso(now)
    qdir = os.path.join(quarantine, ts.replace(":", "").replace("-", "")[:15] + "_" + group)
    os.makedirs(qdir, exist_ok=True)
    moved, total = [], 0
    for p, size, mt in cands:
        rel = os.path.relpath(p, root)
        dest = os.path.join(qdir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        try:
            shutil.move(p, dest)
        except OSError:
            continue  # ملف مقفل أو مفتوح: يُترك في مكانه
        moved.append({"rel": rel.replace("\\", "/"), "bytes": size, "mtime": mt})
        total += size
    with open(os.path.join(qdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"ts": ts, "group": group, "days": days, "root": root, "files": moved}, f, ensure_ascii=False)
    cur = con.execute("INSERT INTO storage_actions(ts, action, grp, days, files, bytes, qdir, status) VALUES (?,?,?,?,?,?,?,?)",
                      (ts, "quarantine", group, days, len(moved), total, qdir, "quarantined"))
    con.commit()
    return {"ok": True, "files": len(moved), "bytes": total, "id": cur.lastrowid, "skipped": len(cands) - len(moved)}


def _qsize(qdir):
    """حجم ملفات الحجر بلا manifest.json."""
    return sum(s for p, s, _m in _walk_files(qdir) if os.path.basename(p) != "manifest.json")


def _action(con, action_id):
    row = con.execute("SELECT id, qdir, status, grp FROM storage_actions WHERE id=?", (int(action_id),)).fetchone()
    if not row:
        raise ValueError("عملية غير موجودة")
    return row


def restore(action_id, con, root=ROOT, quarantine=QUARANTINE, now=None):
    """يعيد ملفات حجر إلى أماكنها (ما لم يظهر ملف جديد مكانها) ويعلّم العملية restored."""
    aid, qdir, status, grp = _action(con, action_id)
    if status != "quarantined" or not _inside(qdir, quarantine):
        raise ValueError("الحجر ليس قابلًا للاسترجاع")
    with open(os.path.join(qdir, "manifest.json"), encoding="utf-8") as f:
        man = json.load(f)
    back, total = 0, 0
    for item in man["files"]:
        src = os.path.join(qdir, item["rel"])
        dest = os.path.join(root, item["rel"])
        if not os.path.exists(src) or os.path.exists(dest) or not _inside(dest, root):
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(src, dest)
        back += 1
        total += item["bytes"]
    shutil.rmtree(qdir, ignore_errors=True)
    con.execute("INSERT INTO storage_actions(ts, action, grp, days, files, bytes, qdir, status) VALUES (?,?,?,?,?,?,?,?)",
                (_iso(now or time.time()), "restore", grp, 0, back, total, qdir, "done"))
    con.execute("UPDATE storage_actions SET status='restored' WHERE id=?", (aid,))
    con.commit()
    return {"ok": True, "files": back, "bytes": total}


def purge(action_id, con, quarantine=QUARANTINE, now=None):
    """حذف نهائي لمجلد حجر واحد (لا رجعة) ويعلّم العملية purged."""
    aid, qdir, status, grp = _action(con, action_id)
    if status != "quarantined" or not _inside(qdir, quarantine) or not os.path.isdir(qdir):
        raise ValueError("الحجر ليس قابلًا للإفراغ")
    size = _qsize(qdir)
    shutil.rmtree(qdir)
    con.execute("INSERT INTO storage_actions(ts, action, grp, days, files, bytes, qdir, status) VALUES (?,?,?,?,?,?,?,?)",
                (_iso(now or time.time()), "purge", grp, 0, 0, size, qdir, "done"))
    con.execute("UPDATE storage_actions SET status='purged' WHERE id=?", (aid,))
    con.commit()
    return {"ok": True, "bytes": size}


def quarantine_rows(con):
    rows = []
    for aid, ts, action, grp, days, files, nbytes, qdir, status in con.execute(
            "SELECT id, ts, action, grp, days, files, bytes, qdir, status FROM storage_actions ORDER BY id DESC LIMIT 60"):
        on_disk = _qsize(qdir) if status == "quarantined" and os.path.isdir(qdir) else 0
        rows.append({"id": aid, "ts": ts, "action": action, "grp": grp, "days": days, "files": files, "bytes": nbytes, "status": status, "disk": on_disk})
    return rows


def handle(op, params, con, root=ROOT, quarantine=QUARANTINE):
    """مدخل الخادم: scan/plan/apply/restore/purge؛ التغييرات تتطلّب confirm=true من الصفحة."""
    if op == "scan":
        return run(con, root, force=True)
    if op == "plan":
        return plan(str(params.get("group", "")), params.get("days", 0), root, con)
    if params.get("confirm") is not True:
        raise ValueError("يلزم تأكيد صريح")
    if op == "apply":
        return apply(str(params.get("group", "")), params.get("days", 0), con, root, quarantine)
    if op == "restore":
        return restore(params.get("id"), con, root, quarantine)
    if op == "purge":
        return purge(params.get("id"), con, quarantine)
    raise ValueError("عملية غير معروفة")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    s = scan()
    print(json.dumps({"ts": s["ts"], "seconds": s["seconds"], "bytes": s["total"]["bytes"], "files": s["total"]["files"],
                      "top": {k: v["bytes"] for k, v in sorted(s["top"].items(), key=lambda kv: -kv[1]["bytes"])[:8]}}, ensure_ascii=False))
