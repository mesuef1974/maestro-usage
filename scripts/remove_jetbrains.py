"""إزالة بقايا JetBrains/PyCharm على مستوى المستخدم (بلا صلاحية مدير). عرض افتراضي؛ --apply للحذف.
يحذف: إعدادات وكاش JetBrains في AppData وملف تفريغ الذاكرة وملفات .jetbrains ومشروع PyCharmMiscProject المؤقت ومجلدات .idea في مشاريعك،
ومفاتيح HKCU الخاصة بالشركة. يستثني عمدًا مجلد .idea في D:\\shschool_mvp (مستودع المنصة لا يُكتب فيه إلا بأمر صريح).
إلغاء تثبيت البرنامج نفسه والخدمة ومجلدات Program Files تحتاج صلاحية مدير ولا يفعلها هذا السكربت.
الاستعمال: python scripts/remove_jetbrains.py [--apply]"""
import argparse
import os
import shutil
import subprocess
import sys
import time

H = os.path.expanduser("~")
FIXED = [
    H + r"\AppData\Roaming\JetBrains", H + r"\AppData\Local\JetBrains", H + r"\AppData\LocalLow\JetBrains",
    H + r"\.jetbrains", H + r"\java_error_in_pycharm.hprof", H + r"\PyCharmMiscProject", H + r"\PycharmProjects",
]
REG = [r"HKCU\SOFTWARE\JetBrains", r"HKCU\SOFTWARE\JavaSoft\Prefs\jetbrains"]
SKIP = {"node_modules", ".git", "site-packages", "__pycache__", "windows", "$recycle.bin", "system volume information", "appdata",
        ".venv", "venv", ".codex", ".lmstudio", ".claude", ".cache", ".conda", ".cargo", ".rustup"}
EXCLUDE_IDEA = {os.path.normcase(r"D:\shschool_mvp\.idea")}


def size(p):
    if os.path.isfile(p):
        return os.lstat(p).st_size
    t = 0
    for r, _ds, fs in os.walk(p):
        for f in fs:
            try:
                t += os.lstat(os.path.join(r, f)).st_size
            except OSError:
                pass
    return t


def find_idea():
    out, t0 = [], time.time()
    for root in (H, "D:/"):
        for r, ds, _fs in os.walk(root):
            if ".idea" in ds:
                out.append(os.path.normpath(os.path.join(r, ".idea")))
            ds[:] = [d for d in ds if d.lower() not in SKIP and d != ".idea" and not d.startswith("$")]
            if time.time() - t0 > 300:
                break
    return out


def rm(p):
    if os.path.isdir(p) and not os.path.islink(p):
        shutil.rmtree(p, ignore_errors=True)
    elif os.path.exists(p):
        try:
            os.remove(p)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    total = freed = 0
    targets = [p for p in FIXED if os.path.exists(p)]
    idea = [p for p in find_idea() if os.path.normcase(p) not in EXCLUDE_IDEA]
    for p in targets + idea:
        s = size(p)
        total += s
        if s >= 1e6 or p in targets:
            print("%8.0f MB  %s" % (s / 1e6, p))
        if a.apply:
            rm(p)
            freed += s - (size(p) if os.path.exists(p) else 0)
    print("مجلدات .idea: %d (مستثنى: shschool_mvp)" % len(idea))
    for k in REG:
        print("سجل:", k)
        if a.apply:
            subprocess.run(["reg", "delete", k, "/f"], capture_output=True)
    print("المجموع %.2f GB (%s)" % (total / 1e9, ("حُذف فعليًّا %.2f GB" % (freed / 1e9)) if a.apply else "عرض فقط؛ أضف --apply"))


if __name__ == "__main__":
    main()
