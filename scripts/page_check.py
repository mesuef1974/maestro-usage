"""فحص كل صفحات reports: أخطاء الكونسول، الفيض الأفقي، وجود العناوين، بعرض 375 و1440. يستعمل Playwright."""
import os
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")
bad = 0
with sync_playwright() as p:
    b = p.chromium.launch()
    for f in sorted(x for x in os.listdir(ROOT) if x.endswith(".html")):
        for w in (375, 1440):
            pg = b.new_page(viewport={"width": w, "height": 900})
            errs = []
            pg.on("console", lambda m, e=errs: e.append(m.text) if m.type in ("error", "warning") else None)
            pg.on("pageerror", lambda x, e=errs: e.append("PE " + str(x)))
            pg.goto("file:///" + os.path.abspath(os.path.join(ROOT, f)).replace("\\", "/"))
            pg.wait_for_timeout(400)
            sw, iw, h1 = pg.evaluate("[document.documentElement.scrollWidth, innerWidth, document.querySelectorAll('h1').length]")
            ok = not errs and sw <= iw and h1 == 1
            bad += not ok
            print("OK " if ok else "BAD", f, w, "overflow" if sw > iw else "", errs[:2])
            pg.close()
    b.close()
sys.exit(1 if bad else 0)
