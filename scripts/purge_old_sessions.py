"""حذف سجلات الجلسات القديمة من ~/.claude/projects بعد التأكد أن لكل ملف نسخة مطابقة بالحجم في فرع git محلي (الافتراضي legacy-local).
عرض فقط افتراضيًّا؛ --apply ينسخ القاعدة احتياطيًّا ثم يحذف. لا يحذف ما ليس له نسخة مطابقة في git، ولا ما أحدث من --days.
ملاحظة: الفرع المحلي ليس على GitHub، والنسخة باقية داخل ~/.claude/.git نفسه (لا يصغّره الحذف).
الاستعمال: python scripts/purge_old_sessions.py [--days 30] [--ref legacy-local] [--apply]"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
CLAUDE = os.path.join(HOME, ".claude")
PROJECTS = os.path.join(CLAUDE, "projects")
DB = os.path.join(HOME, ".maestro", "flow_usage.sqlite3")


def git_sizes(ref):
    """{مسار نسبي من projects: حجم الكائن} للملفات jsonl في الفرع."""
    out = subprocess.run(["git", "-C", CLAUDE, "ls-tree", "-r", "-l", "-z", ref, "projects"], capture_output=True, encoding="utf-8").stdout
    res = {}
    for rec in out.split("\0"):
        if not rec or not rec.endswith(".jsonl"):
            continue
        meta, path = rec.split("\t", 1)
        res[path[len("projects/"):]] = int(meta.split()[3])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--ref", default="legacy-local")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    now = time.time()
    in_git = git_sizes(a.ref)
    safe, keep_nocopy, keep_diff = [], [], []
    for r, _ds, fs in os.walk(PROJECTS):
        for f in fs:
            if not f.endswith(".jsonl"):
                continue
            p = os.path.join(r, f)
            st = os.stat(p)
            if (now - st.st_mtime) / 86400 <= a.days:
                continue
            rel = os.path.relpath(p, PROJECTS).replace("\\", "/")
            if rel not in in_git:
                keep_nocopy.append((p, st.st_size))
            elif in_git[rel] != st.st_size:
                keep_diff.append((p, st.st_size))
            else:
                safe.append((p, st.st_size))
    def mb(files):
        return "%d ملفًا %.0f MB" % (len(files), sum(s for _p, s in files) / 1e6)

    print("يُحذف (نسخة مطابقة بالحجم في %s): %s" % (a.ref, mb(safe)))
    print("يُبقى (لا نسخة في git): %s" % mb(keep_nocopy))
    print("يُبقى (نسخة git بحجم مختلف): %s" % mb(keep_diff))
    if not a.apply:
        print("عرض فقط؛ أضف --apply للحذف")
        return
    bk = os.path.join(HOME, ".maestro", "backups")
    os.makedirs(bk, exist_ok=True)
    dest = os.path.join(bk, "flow_usage_before_purge_%s.sqlite3" % time.strftime("%Y%m%d_%H%M%S"))
    shutil.copyfile(DB, dest)
    print("نسخة القاعدة:", dest)
    n = 0
    for p, _s in safe:
        try:
            os.remove(p)
            n += 1
        except OSError:
            pass
    for r, ds, _fs in os.walk(PROJECTS, topdown=False):  # المجلدات الفارغة فقط
        for d in ds:
            try:
                os.rmdir(os.path.join(r, d))
            except OSError:
                pass
    print("حُذف %d ملفًا" % n)


if __name__ == "__main__":
    main()
