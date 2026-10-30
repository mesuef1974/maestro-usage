"""حذف كاش puppeteer وnpm وتقارير الانهيار ونسخ القاعدة الاحتياطية عدا الأحدث. عرض افتراضي؛ --apply للحذف.
الكاش يُعاد بناؤه عند الحاجة؛ الملفات المقفلة تُترك. من .maestro\\backups تُبقى النسخة الأحدث بوقت التعديل.
الاستعمال: python scripts/clean_caches.py [--apply]"""
import argparse
import os
import shutil
import sys

HOME = os.path.expanduser("~")
DIRS = [
    os.path.join(HOME, ".cache", "puppeteer"),
    os.path.join(HOME, "AppData", "Local", "npm-cache"),
    os.path.join(HOME, "AppData", "Local", "CrashDumps"),
]
BACKUPS = os.path.join(HOME, ".maestro", "backups")


def size(p):
    t = 0
    for r, _ds, fs in os.walk(p):
        for f in fs:
            try:
                t += os.lstat(os.path.join(r, f)).st_size
            except OSError:
                pass
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    total = freed = 0
    for d in DIRS:
        if not os.path.isdir(d):
            continue
        s = size(d)
        total += s
        print("%8.0f MB  %s" % (s / 1e6, d))
        if a.apply:
            for e in os.scandir(d):  # محتويات المجلد لا المجلد نفسه
                if e.is_dir(follow_symlinks=False):
                    shutil.rmtree(e.path, ignore_errors=True)
                else:
                    try:
                        os.remove(e.path)
                    except OSError:
                        pass
            freed += s - size(d)
    files = sorted((e for e in os.scandir(BACKUPS) if e.is_file()), key=lambda e: e.stat().st_mtime, reverse=True)
    print("تُبقى نسخة القاعدة الأحدث:", files[0].name if files else "لا نسخ")
    for e in files[1:]:
        s = e.stat().st_size
        total += s
        print("%8.0f MB  backups\\%s" % (s / 1e6, e.name))
        if a.apply:
            try:
                os.remove(e.path)
                freed += s
            except OSError:
                pass
    print("المجموع %.2f GB (%s)" % (total / 1e9, ("حُذف فعليًّا %.2f GB" % (freed / 1e9)) if a.apply else "عرض فقط؛ أضف --apply"))


if __name__ == "__main__":
    main()
