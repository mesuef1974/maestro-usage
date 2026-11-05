"""تدقيق مقابض توفير التوكنز: أحجام مصادر السياق الثابت وحالة المهارات والإعدادات. قراءة فقط، صفر توكنات، ولا يُطبع أي محتوى.

التقدير تقريبي: الأحرف اللاتينية ≈ 4 لكل توكن، وغيرها (العربية) ≈ 1.8 لكل توكن.
المهارة المفعّلة تُحمَّل بالاسم والوصف، و«name-only» بالاسم، و«off» لا تُحمَّل (المفتاح skillOverrides).
"""
import json
import os
import re
import sqlite3
import sys

HOME = os.path.expanduser("~")
CLAUDE = os.path.join(HOME, ".claude")
DB = os.path.join(HOME, ".maestro", "flow_usage.sqlite3")
FRONT = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.S)


def est(text):
    ascii_n = sum(1 for c in text if ord(c) < 128)
    return round(ascii_n / 4 + (len(text) - ascii_n) / 1.8)


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def front(text):
    """(اسم، وصف) من ترويسة المهارة؛ يُقرأ الحقلان فقط."""
    m = FRONT.match(text or "")
    out = {}
    if m:
        for key in ("name", "description"):
            k = re.search(r"^%s:\s*(.*?)(?=^\w[\w-]*:|\Z)" % key, m.group(1), re.S | re.M)
            if k:
                out[key] = " ".join(k.group(1).split()).strip("\"'>|- ")
    return out.get("name"), out.get("description") or ""


def settings():
    t = read(os.path.join(CLAUDE, "settings.json"))
    return json.loads(t) if t else {}


def project_dirs():
    """مجلدات المشاريع الحديثة من القاعدة (بلا worktrees) ثم تلك التي لها مجلد .claude."""
    out = []
    try:
        con = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
        rows = [r[0] for r in con.execute("SELECT DISTINCT cwd FROM sessions WHERE cwd IS NOT NULL ORDER BY last_seen DESC LIMIT 200")]
        con.close()
    except sqlite3.Error:
        rows = []
    for cwd in rows:
        n = os.path.normpath(cwd)
        if ".claude" + os.sep + "worktrees" in n or not os.path.isdir(n) or n in out:
            continue
        out.append(n)
    return out


def skills_in(root):
    """[(اسم، حجم الوصف بالتقدير، حجم الاسم)] لكل SKILL.md تحت root."""
    res = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return res
    for n in names:
        t = read(os.path.join(root, n, "SKILL.md"))
        if t is None:
            continue
        nm, desc = front(t)
        res.append((nm or n, est(desc), est(nm or n), est(t)))
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    st = settings()
    ov = st.get("skillOverrides", {})
    rows = []  # (فئة، عنصر، توكنات)

    def add(cat, item, tok):
        rows.append((cat, item, tok))

    g = read(os.path.join(CLAUDE, "CLAUDE.md"))
    add("تعليمات", "CLAUDE.md العام", est(g) if g else 0)
    for d in project_dirs():
        label = os.path.basename(d)
        for rel in ("CLAUDE.md", "CLAUDE.local.md"):
            t = read(os.path.join(d, rel))
            if t:
                add("تعليمات", "%s/%s" % (label, rel), est(t))
        rules = os.path.join(d, ".claude", "rules")
        if os.path.isdir(rules):
            for r in sorted(os.listdir(rules)):
                t = read(os.path.join(rules, r))
                if t and not re.search(r"^paths:", FRONT.match(t).group(1) if FRONT.match(t) else "", re.M):
                    add("قواعد", "%s/.claude/rules/%s" % (label, r), est(t))
    proj_root = os.path.join(CLAUDE, "projects")
    for p in sorted(os.listdir(proj_root)) if os.path.isdir(proj_root) else []:
        t = read(os.path.join(proj_root, p, "memory", "MEMORY.md"))
        if t:
            add("ذاكرة", "MEMORY.md · " + p, est(t))

    skill_sets = [("مهارة (مستخدم)", os.path.join(CLAUDE, "skills"))]
    skill_sets += [("مهارة (%s)" % os.path.basename(d), os.path.join(d, ".claude", "skills")) for d in project_dirs()]
    for cat, root in skill_sets:
        for nm, dtok, ntok, _full in skills_in(root):
            mode = ov.get(nm, "on")
            add(cat, "%s [%s]" % (nm, mode), 0 if mode == "off" else ntok if mode == "name-only" else ntok + dtok)
    cmds = os.path.join(CLAUDE, "commands")
    if os.path.isdir(cmds):
        for c in sorted(os.listdir(cmds)):
            t = read(os.path.join(cmds, c))
            if t:
                add("أمر", "/" + c[:-3], est(front(t)[1]) + est(c))

    shared = sum(t for c, i, t in rows if i == "CLAUDE.md العام" or c in ("أمر", "مهارة (مستخدم)"))
    print("== تقدير ما يُحمَّل في بدء الجلسة، لكل مشروع (بالتوكن) ==")
    print("مشترك بين المشاريع (CLAUDE.md العام + مهارات المستخدم + الأوامر): %d" % shared)
    measured = {}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
        for proj, ctx in con.execute("SELECT proj, ctx FROM startup_samples WHERE ctx < 60000 AND ts >= date('now','-14 day') ORDER BY ctx"):
            measured.setdefault(proj, []).append(ctx)
        con.close()
    except sqlite3.Error:
        pass
    print("%-34s %7s %7s %8s %5s" % ("المشروع", "محلي", "مقيس", "المتبقي", "جلسات"))
    for d in project_dirs():
        enc = re.sub(r"[^A-Za-z0-9]", "-", d)
        v = measured.get(enc)
        if not v:
            continue
        base = os.path.basename(d)
        own = sum(t for c, i, t in rows if i.startswith(base + "/") or i == "MEMORY.md · " + enc or c == "مهارة (%s)" % base)
        print("%-34s %7d %7d %8d %5d" % (base[:32], shared + own, v[len(v) // 2], v[len(v) // 2] - shared - own, len(v)))
    print("(المتبقي = نصّ النظام وتعريفات الأدوات وما تحقنه الخطّافات والموصلات؛ لا يُضبط بالتعليمات.)")
    print("\n== أكبر 15 عنصرًا ==")
    for cat, item, tok in sorted(rows, key=lambda r: -r[2])[:15]:
        print("%6d  %-14s %s" % (tok, cat, item))
    print("\n== مهارات مفعّلة بالوصف الكامل (قابلة للتحويل إلى name-only أو off) ==")
    on = [(i, t) for c, i, t in rows if c.startswith("مهارة") and "[on]" in i and t]
    for i, t in sorted(on, key=lambda x: -x[1])[:15]:
        print("%6d  %s" % (t, i))
    print("(%d مهارة بالوصف الكامل، مجموعها %d)" % (len(on), sum(t for _i, t in on)))

    print("\n== مقابض الإعدادات ==")
    keys = ("model", "effortLevel", "autoCompactWindow", "promptSuggestionEnabled", "alwaysThinkingEnabled", "includeCoAuthoredBy", "outputStyle", "agent")
    for k in keys:
        print("%-26s %s" % (k, st.get(k, "— (الافتراضي)")))
    print("%-26s %s" % ("env", ", ".join("%s=%s" % kv for kv in st.get("env", {}).items()) or "—"))
    print("%-26s %s" % ("claudeMdExcludes", len(st.get("claudeMdExcludes", []))))
    en = st.get("enabledPlugins", {})
    print("%-26s مفعّلة %d · معطّلة %d" % ("enabledPlugins", sum(1 for v in en.values() if v), sum(1 for v in en.values() if not v)))
    hooks = st.get("hooks", {})
    print("%-26s %s" % ("hooks (حدث:عدد)", ", ".join("%s:%d" % (k, len(v)) for k, v in hooks.items()) or "—"))
    for ev in ("SessionStart", "UserPromptSubmit"):
        names = [h.get("command", "").replace("\\", "/").split("/")[-1] for g in hooks.get(ev, []) for h in g.get("hooks", [])]
        print("%-26s %s" % (ev, " · ".join(names) or "—"))
    print("(مخرجات خطّافات البدء تُحقن في السياق؛ لم تُشغَّل هنا.)")


if __name__ == "__main__":
    main()
