"""تنظيف مجلد Temp (عدا claude وما تستعمله عملية حيّة) وحذف نموذج Qwen3-8B من LM Studio. عرض افتراضي؛ --apply للحذف.
يُبقي Temp\\claude (بيئتا scratchpad المحميتان وملفات الجلسة) ونموذج Qwen3-VL-4B. الملفات المقفلة تُترك ولا تُكسر.
الاستعمال: python scripts/clean_temp_and_models.py [--apply]"""
import argparse
import os
import shutil
import subprocess
import sys

HOME = os.path.expanduser("~")
TEMP = os.path.join(HOME, "AppData", "Local", "Temp")
KEEP_TEMP = {"claude"}
MODEL = os.path.join(HOME, ".lmstudio", "models", "lmstudio-community", "Qwen3-8B-GGUF")


def size(p):
    t = 0
    for r, _ds, fs in os.walk(p):
        for f in fs:
            try:
                t += os.lstat(os.path.join(r, f)).st_size
            except OSError:
                pass
    return t


def live_text():
    """نص أوامر وملفات العمليات الحيّة بحروف صغيرة لمطابقة أسماء مجلدات Temp."""
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process | ForEach-Object { $_.CommandLine + ' ' + $_.ExecutablePath }"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    return (out or "").lower().replace("\\", "/")


def rm(p):
    if os.path.isdir(p) and not os.path.islink(p):
        shutil.rmtree(p, ignore_errors=True)
    else:
        try:
            os.remove(p)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    live = live_text()
    freed = total = 0
    for e in sorted(os.scandir(TEMP), key=lambda x: x.name.lower()):
        if e.name.lower() in KEEP_TEMP:
            continue
        if e.name.lower() in live:
            print("قيد الاستعمال، يُترك:", e.name)
            continue
        s = size(e.path) if e.is_dir(follow_symlinks=False) else e.stat().st_size
        total += s
        if s >= 20e6:
            print("%8.0f MB  Temp\\%s" % (s / 1e6, e.name))
        if a.apply:
            rm(e.path)
            left = size(e.path) if os.path.isdir(e.path) else (os.lstat(e.path).st_size if os.path.exists(e.path) else 0)
            freed += s - left
    if os.path.isdir(MODEL):
        s = size(MODEL)
        total += s
        print("%8.0f MB  Qwen3-8B-GGUF (LM Studio)" % (s / 1e6))
        if a.apply:
            shutil.rmtree(MODEL, ignore_errors=True)
            freed += s - (size(MODEL) if os.path.isdir(MODEL) else 0)
    print("المجموع %.2f GB (%s)" % (total / 1e9, ("حُذف فعليًّا %.2f GB" % (freed / 1e9)) if a.apply else "عرض فقط؛ أضف --apply"))


if __name__ == "__main__":
    main()
