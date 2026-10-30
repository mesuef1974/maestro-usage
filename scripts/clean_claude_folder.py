"""تنظيف الملفات الآمنة في مجلد كلود وبيانات التطبيق: يعرض أولًا ما سيُحذف (تجفيف) ولا يحذف إلا بـ --apply.
لا يمسّ projects ولا .git ولا Azkia ولا skills ولا settings. الكاش الثقيل (Code Cache وCache وGrShaderCache) يُحذف بـ --app-cache والتطبيق مغلق.
الاستعمال: python scripts/clean_claude_folder.py            (عرض فقط)
           python scripts/clean_claude_folder.py --apply    (حذف)
           python scripts/clean_claude_folder.py --apply --app-cache   (والتطبيق مغلق تمامًا)"""
import argparse
import os
import shutil
import sys
import time

H = os.path.expanduser("~/.claude")
A = os.path.expandvars(r"%APPDATA%\Claude")
NOW = time.time()


def walk_files(base):
    for r, _ds, fs in os.walk(base):
        for f in fs:
            yield os.path.join(r, f)


def old_files(base, days):
    out = []
    for p in walk_files(base) if os.path.isdir(base) else []:
        try:
            st = os.stat(p)
        except OSError:
            continue
        if (NOW - st.st_mtime) / 86400 > days:
            out.append((p, st.st_size))
    return out


def whole_dir(base):
    return [(p, os.stat(p).st_size) for p in walk_files(base)] if os.path.isdir(base) else []


def targets(app_cache):
    t = [
        ("projects-archive-2026-04-17 (نسخة منه في تاريخ git)", whole_dir(os.path.join(H, "projects-archive-2026-04-17"))),
        ("backups أقدم من 14 يومًا", old_files(os.path.join(H, "backups"), 14)),
        ("plugins/.trash", whole_dir(os.path.join(H, "plugins", ".trash"))),
        ("AppData logs أقدم من 7 أيام", old_files(os.path.join(A, "logs"), 7)),
    ]
    for d in ("shell-snapshots", "logs", "cache", "telemetry"):
        t.append((d + " أقدم من يومين", old_files(os.path.join(H, d), 2)))
    if app_cache:
        for d in ("Code Cache", "Cache", "GrShaderCache"):
            t.append(("AppData\\" + d, whole_dir(os.path.join(A, d))))
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--app-cache", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    total = 0
    for label, files in targets(a.app_cache):
        mb = sum(s for _p, s in files) / 1e6
        total += mb
        print("%-55s %8.1f MB %6d ملف" % (label, mb, len(files)))
        if a.apply:
            for p, _s in files:
                try:
                    os.remove(p)
                except OSError:
                    pass  # مقفل (قيد الاستعمال): يُترك
    arch = os.path.join(H, "projects-archive-2026-04-17")
    if a.apply and os.path.isdir(arch):
        shutil.rmtree(arch, ignore_errors=True)
    print("المجموع %.1f MB (%s)" % (total, "حُذف" if a.apply else "عرض فقط؛ أضف --apply للحذف"))


if __name__ == "__main__":
    main()
