"""حذف بيئات بايثون الخاملة المحدَّدة بقائمة صريحة (لا بحث ولا حذف بنمط). عرض افتراضي؛ --apply للحذف.
قبل حذف كل بيئة يحفظ قائمة حزمها (اسم==نسخة من dist-info) في ~/.maestro/venv_freezes لإمكان إعادة بنائها، ويرفض ما ليس فيه pyvenv.cfg.
خارج القائمة عمدًا: بيئات shschool_mvp وquality-runtime والبيئات المؤقتة وأدوات pipx للفحص (ruff وpre-commit وblack وpoetry) وuv وLM Studio وكاش pre-commit.
الاستعمال: python scripts/remove_idle_venvs.py [--apply]"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HOME = os.path.expanduser("~").replace("\\", "/")
FREEZES = HOME + "/.maestro/venv_freezes"
VENVS = [
    "D:/llm-math-representation-geometry/.venv",
    "D:/ant-neural-reasoner/.venv",
    HOME + "/PyCharmMiscProject/.venv",
    "D:/pro_00123/.venv",
    "D:/Azkia/projects/mahsoos/.venv",
    HOME + "/Projects/schoolos-template/backend/.venv",
    "D:/Azkia/projects/manhaj-graph/.venv",
    "D:/pvg_axis_search_v6_5_low_storage_tail/.venv",
    HOME + "/crypto_mypy_work/venv",
    "D:/paper_mersenne_ladder/paper_E5/web/.venv",
    "D:/ant-pvg-research-observatory/.venv",
    "D:/PVG-Explorer/.venv",
    "D:/analytic-number-theory-encyclopedia-ar/.venv",
    "D:/ant_pvg_local_observatory/.venv",
    "D:/PVG-ANT-Inverse-Geometry-001/.venv",
    HOME + "/PVG-What-is/.venv",
    "D:/PVG-ANT-Central-Mind/.venv",
]
PIPX_TOOLS = ["manim", "jupyterlab", "httpie"]  # تُزال بـ pipx uninstall لتبقى بياناته متّسقة


def size(p):
    t = 0
    for r, _ds, fs in os.walk(p):
        for f in fs:
            try:
                t += os.stat(os.path.join(r, f)).st_size
            except OSError:
                pass
    return t


def live_paths():
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | Where-Object {$_.ExecutablePath} | ForEach-Object { $_.ExecutablePath }"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    return [x.strip().replace("\\", "/").lower() for x in out.splitlines() if x.strip()]


def freeze(venv):
    sp = os.path.join(venv, "Lib", "site-packages")
    pk = []
    if os.path.isdir(sp):
        for d in sorted(os.listdir(sp)):
            if d.endswith(".dist-info"):
                pk.append(d[:-len(".dist-info")].replace("-", "==", 1))
    return pk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    live = live_paths()
    total = freed = 0
    os.makedirs(FREEZES, exist_ok=True)
    for v in VENVS:
        if not os.path.isfile(v + "/pyvenv.cfg"):
            print("غير موجودة أو ليست بيئة، تُتخطّى:", v)
            continue
        if any(x.startswith(v.lower() + "/") for x in live):
            print("قيد التشغيل، تُتخطّى:", v)
            continue
        s = size(v)
        total += s
        print("%8.0f MB  %s" % (s / 1e6, v))
        if a.apply:
            name = v.replace(":", "").replace("/", "_").strip("_") + ".txt"
            with open(os.path.join(FREEZES, name), "w", encoding="utf-8") as f:
                f.write("# %s | حُذفت %s\n" % (v, time.strftime("%Y-%m-%d")))
                f.write("\n".join(freeze(v)) + "\n")
            shutil.rmtree(v, ignore_errors=True)
            if not os.path.exists(v):
                freed += s
    for t in PIPX_TOOLS:
        print("pipx uninstall", t)
        if a.apply:
            subprocess.run(["pipx", "uninstall", t], capture_output=True)
    print("المجموع %.2f GB (%s)" % (total / 1e9, ("حُذف منها %.2f GB" % (freed / 1e9)) if a.apply else "عرض فقط؛ أضف --apply"))


if __name__ == "__main__":
    main()
