"""كلفة بدء الجلسة وأثر كل تعديل في مصادر السياق الثابت عليها.

- startup_samples: سياق أول ردّ رئيس لكل جلسة (يُملأ من usage_turns تزايديًّا).
- config_fingerprints: بصمة (SHA-256) وحجم كل مصدر سياق ثابت كل دورة؛ تغيّر البصمة = تعديل بزمنه الدقيق. لا يُحفظ المحتوى.
- effects: مقارنة وسيط آخر K جلسة جديدة قبل التعديل بأول K بعده، في النطاق نفسه (مجلد المشروع أو الكل).
الإعداد يُقرأ عند بدء الجلسة، لذا المقارنة بالجلسات لا بالأيام. الجلسات المستأنفة (سياق أول ردّ ≥ FRESH_MAX) مستبعدة.
"""
import hashlib
import json
import math
import os
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sessions_page  # noqa: E402
import usage_db  # noqa: E402

HOME = os.path.expanduser("~")
CLAUDE_DIR = os.path.join(HOME, ".claude")
PROJECTS = os.path.join(CLAUDE_DIR, "projects")
FRESH_MAX = 60_000  # أول ردّ بسياق أكبر يُعدّ جلسة مستأنفة لا بدءًا جديدًا (أحكام الأثر)
CHART_FRESH_MAX = 110_000  # سقف الرسم التاريخي وحده: قبل 10/25 كان البدء 77–98 ألفًا؛ بأمر المالك ولا يمسّ أحكام الأثر
K = 20  # حجم نافذة المقارنة (جلسات)
MIN_N = 15
MIN_DELTA = 3_000  # فرق الوسيط الأدنى (توكن) ليُعدّ أثرًا
SE_MULT = 2.0
SETTINGS_KEYS = ("enabledPlugins", "skillOverrides", "env", "model", "autoCompactWindow", "claudeMdExcludes", "hooks",
                 "statusLine", "outputStyle", "agent", "effortLevel", "syncClaudeAiSkills", "syncClaudeAiPlugins", "disableClaudeAiConnectors",
                 "disableBundledSkills", "includeGitInstructions", "skillListingBudgetFraction", "skillListingMaxDescChars",
                 "disableSkillShellExecution")  # مفاتيح تؤثر في سياق البدء؛ permissions خارجها لأنها تتغيّر بكل موافقة
RECENT_DAYS = 14
ITEM_NAMES = {"settings:startup": "إعدادات البدء", "claudemd:global": "CLAUDE.md العام", "skills:user": "مهارات المستخدم",
              "memory:core": "ذاكرة core"}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _file(path):
    try:
        with open(path, "rb") as f:
            b = f.read()
        return _sha(b), len(b)
    except OSError:
        return None


def _settings_item():
    try:
        with open(os.path.join(CLAUDE_DIR, "settings.json"), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    sub = {k: d[k] for k in SETTINGS_KEYS if k in d}
    b = json.dumps(sub, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return _sha(b), len(b)


def _skills_item():
    root = os.path.join(CLAUDE_DIR, "skills")
    parts = []
    try:
        for name in sorted(os.listdir(root)):
            p = os.path.join(root, name, "SKILL.md")
            if os.path.isfile(p):
                parts.append("%s:%d" % (name, os.path.getsize(p)))
    except OSError:
        return None
    b = "\n".join(parts).encode("utf-8")
    return _sha(b), len(b)


def _memory_core_item():
    root = os.path.join(CLAUDE_DIR, "improve_claude", "memory", "core")
    try:
        names = sorted(n for n in os.listdir(root) if n.endswith(".md"))
        blobs = []
        for n in names:
            with open(os.path.join(root, n), "rb") as f:
                blobs.append(f.read())
    except OSError:
        return None
    return _sha(b"\0".join(blobs)), sum(len(x) for x in blobs)


def fingerprint_items(con):
    """{بند: (بصمة، حجم)}؛ البنود الغائبة تُحذف."""
    out = {"settings:startup": _settings_item(), "claudemd:global": _file(os.path.join(CLAUDE_DIR, "CLAUDE.md")),
           "skills:user": _skills_item(), "memory:core": _memory_core_item()}
    since = (datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for (cwd,) in con.execute("SELECT DISTINCT cwd FROM sessions WHERE cwd IS NOT NULL AND last_seen >= ?", (since,)).fetchall():
        label = sessions_page.folder_label(cwd)
        if label and os.path.isdir(cwd):
            out.setdefault("claudemd:folder:" + label, _file(os.path.join(cwd, "CLAUDE.md")))
    for (proj,) in con.execute("SELECT DISTINCT proj FROM startup_samples WHERE ts >= ? AND proj IS NOT NULL", (since,)).fetchall():
        out["memory:proj:" + proj] = _file(os.path.join(PROJECTS, proj, "memory", "MEMORY.md"))
    return {k: v for k, v in out.items() if v}


def check_fingerprints(con, now=None, items=None):
    """يسجّل خط أساس لكل بند جديد وتغييرًا لكل بصمة اختلفت؛ يعيد قائمة التغييرات [(بند، حجم قبل، حجم بعد)]."""
    now = now or usage_db.now_iso()
    items = fingerprint_items(con) if items is None else items
    changed = []
    for item, (sha, size) in sorted(items.items()):
        last = con.execute("SELECT sha, bytes FROM config_fingerprints WHERE item=? ORDER BY ts DESC LIMIT 1", (item,)).fetchone()
        if last and last[0] == sha:
            continue
        con.execute("INSERT OR IGNORE INTO config_fingerprints(ts, item, sha, bytes) VALUES (?,?,?,?)", (now, item, sha, size))
        if last:
            changed.append((item, last[1], size))
    con.commit()
    return changed


def _version(source_path):
    try:
        with open(os.path.join(PROJECTS, source_path), encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i > 80:
                    break
                m = re.search(r'"version":"([0-9A-Za-z.\-]{1,30})"', line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


def refresh_samples(con):
    """يضيف عيّنة لكل جلسة جديدة (أول ردّ رئيس)؛ يعيد عدد المضاف."""
    meta = {k: cwd for k, cwd in con.execute("SELECT session_key, cwd FROM sessions")}
    have = {k for (k,) in con.execute("SELECT session_key FROM startup_samples")}
    n = 0
    for key, ts in con.execute("SELECT session_key, MIN(ts) FROM usage_turns WHERE is_sidechain=0 GROUP BY session_key").fetchall():
        if key in have:
            continue
        row = con.execute(
            "SELECT input_tokens, cache_creation_tokens, cache_read_tokens, model, turn_origin, source_path FROM usage_turns "
            "WHERE session_key=? AND is_sidechain=0 AND ts=? ORDER BY message_id LIMIT 1", (key, ts)).fetchone()
        if not row:
            continue
        i, cc, cr, model, org, sp = row
        i, cc, cr = i or 0, cc or 0, cr or 0
        proj = sp.replace("\\", "/").split("/")[0] if sp else None
        con.execute(
            "INSERT OR IGNORE INTO startup_samples(session_key, ts, ctx, input_tokens, cache_creation_tokens, cache_read_tokens, model, origin, "
            "folder, proj, cc_version) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (key, ts, i + cc + cr, i, cc, cr, model, org, sessions_page.folder_label(meta.get(key)) or None, proj, _version(sp) if sp else None))
        n += 1
    con.commit()
    return n


def _fresh(con, scope=None, cap=FRESH_MAX):
    """[(ts, ctx, folder, proj)] للجلسات الجديدة مرتبة بالزمن؛ scope=("folder"|"proj", قيمة) أو None."""
    q = "SELECT ts, ctx, folder, proj FROM startup_samples WHERE ctx < ?"
    args = [cap]
    if scope:
        q += " AND %s = ?" % ("folder" if scope[0] == "folder" else "proj")
        args.append(scope[1])
    return con.execute(q + " ORDER BY ts", args).fetchall()


def _quant(v, p):
    s = sorted(v)
    pos = (len(s) - 1) * p
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _stat(v):
    if not v:
        return None
    med = statistics.median(v)
    iqr = _quant(v, .75) - _quant(v, .25)
    se = 1.253 * (iqr / 1.349) / math.sqrt(len(v)) if len(v) > 1 else None
    return dict(n=len(v), med=med, se=se)


def verdict(b, a):
    """يحكم على فرق وسيطين: pending/lower/higher/inconclusive."""
    if not b or not a or b["n"] < MIN_N or a["n"] < MIN_N:
        return "pending", None
    delta = a["med"] - b["med"]
    se = math.sqrt((b["se"] or 0) ** 2 + (a["se"] or 0) ** 2)
    if abs(delta) >= MIN_DELTA and abs(delta) > SE_MULT * se:
        return ("lower" if delta < 0 else "higher"), delta
    return "inconclusive", delta


def _scope(item):
    if item.startswith("claudemd:folder:"):
        return ("folder", item[len("claudemd:folder:"):])
    if item.startswith("memory:proj:"):
        return ("proj", item[len("memory:proj:"):])
    return None


def _item_label(item):
    if item in ITEM_NAMES:
        return ITEM_NAMES[item]
    if item.startswith("claudemd:folder:"):
        return "CLAUDE.md · " + item[len("claudemd:folder:"):]
    if item.startswith("memory:proj:"):
        return "ذاكرة المشروع · " + item[len("memory:proj:"):]
    return item


def changes(con):
    """التغييرات المكتشفة (بلا خط الأساس) + تغييرات يدوية بمفتاح startup_… في config_changes، مرتبة بالزمن."""
    out = []
    for (item,) in con.execute("SELECT DISTINCT item FROM config_fingerprints").fetchall():
        rows = con.execute("SELECT ts, bytes FROM config_fingerprints WHERE item=? ORDER BY ts", (item,)).fetchall()
        for prev, cur in zip(rows, rows[1:]):
            out.append(dict(ts=cur[0], item=item, label=_item_label(item), scope=_scope(item), b0=prev[1], b1=cur[1]))
    for ts, key in con.execute("SELECT ts, key FROM config_changes WHERE key LIKE 'startup\\_%' ESCAPE '\\'"):
        out.append(dict(ts=ts if "T" in ts else ts + "T00:00:00Z", item=key, label=key, scope=None, b0=None, b1=None))
    return sorted(out, key=lambda c: c["ts"])


def effects(con):
    """أثر كل تعديل: وسيط آخر K جلسة جديدة قبله مقابل أول K بعده (حتى التعديل التالي المؤثر في النطاق نفسه)."""
    chs = changes(con)
    out = []
    for c in chs:
        samples = _fresh(con, c["scope"])
        nxt = next((o["ts"] for o in chs if o["ts"] > c["ts"] and (o["scope"] is None or c["scope"] is None or o["scope"] == c["scope"])), None)
        before = [x[1] for x in samples if x[0] < c["ts"]][-K:]
        after_all = [x[1] for x in samples if x[0] >= c["ts"] and (nxt is None or x[0] < nxt)]
        after = after_all[:K]
        b, a = _stat(before), _stat(after)
        v, delta = verdict(b, a)
        out.append(dict(ts=c["ts"], label=c["label"], scope=(c["scope"][1] if c["scope"] else None), size0=c["b0"], size1=c["b1"],
                        nb=len(before), na=len(after), mb=b and b["med"], ma=a and a["med"], delta=delta, verdict=v,
                        overlap=nxt is not None and len(after_all) < K))
    return out


def daily(con, days=60):
    """وسيط سياق البدء ونطاقه الربيعي لكل يوم (جلسات جديدة فقط)."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    by = {}
    for ts, ctx, _f, _p in _fresh(con, cap=CHART_FRESH_MAX):
        if ts[:10] >= since:
            by.setdefault(ts[:10], []).append(ctx)
    return [dict(d=d, n=len(v), med=round(statistics.median(v)), p25=round(_quant(v, .25)), p75=round(_quant(v, .75)))
            for d, v in sorted(by.items())]


def current(con):
    """مؤشرات الآن: وسيط آخر K جلسة جديدة، وسيط K التي قبلها، الأرضية (5%)، حصتها من متوسط سياق الردّ في 7 أيام، وأكثر المجلدات، وزمن آخر عيّنة."""
    allv = _fresh(con)  # مرتبة بالزمن، فآخر عنصر هو أحدث عيّنة طازجة
    ctxs = [x[1] for x in allv]
    last, prev = ctxs[-K:], ctxs[-2 * K:-K]
    now = datetime.now(timezone.utc)
    since7 = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    avg = con.execute("SELECT AVG(input_tokens + cache_creation_tokens + cache_read_tokens) FROM usage_turns WHERE is_sidechain=0 AND ts >= ?",
                      (since7,)).fetchone()[0]
    since30 = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    folders = {}
    for ts, ctx, f, _p in allv:
        if ts >= since30 and f:
            folders.setdefault(f, []).append(ctx)
    top = sorted(folders.items(), key=lambda kv: -len(kv[1]))[:5]
    med = statistics.median(last) if last else None
    return dict(n=len(last), med=med, prev_n=len(prev), prev_med=statistics.median(prev) if prev else None,
                floor=_quant(ctxs[-200:], .05) if ctxs else None, avg7=avg, share=(med / avg) if med and avg else None,
                last_ts=allv[-1][0] if allv else None,
                folders=[dict(f=f, n=len(v), med=round(statistics.median(v))) for f, v in top])


def payload(con):
    base = con.execute("SELECT MIN(ts) FROM config_fingerprints").fetchone()[0]
    return dict(daily=daily(con), cur=current(con), fx=effects(con), baseline=base, k=K, min_n=MIN_N, min_delta=MIN_DELTA, fresh_max=FRESH_MAX)


def run(con, new_data=True):
    """دورة واحدة: عيّنات الجلسات الجديدة (عند ورود بيانات أو خلوّ الجدول) ثم بصمات المصادر؛ تعيد أرقامًا فقط."""
    try:
        empty = con.execute("SELECT 1 FROM startup_samples LIMIT 1").fetchone() is None
        added = refresh_samples(con) if (new_data or empty) else 0
        ch = check_fingerprints(con)
    except OSError:
        return {"startup": "fail"}
    return {"startup_new": added, "config_changed": len(ch)}


if __name__ == "__main__":
    c = usage_db.connect()
    print(run(c))
    print(json.dumps(current(c), ensure_ascii=False))
    for e in effects(c):
        print(e)
