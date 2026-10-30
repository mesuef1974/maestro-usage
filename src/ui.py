"""أجزاء مشتركة بين صفحات المنصة الذاتية: CSS ودوال JS للرسم، وتهريب JSON، والكتابة الذرّية."""
import json
import os
from pathlib import Path

SRC = Path(__file__).resolve().parent


def assets():
    return (SRC / "ui_common.css").read_text(encoding="utf-8"), (SRC / "ui_common.js").read_text(encoding="utf-8")


def embed_json(data):
    """JSON للتضمين داخل script: يُهرَّب منه '</' وفاصلا الأسطر كي لا يُغلق الوسم ولا يتصدّع النص."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


NAV = [("القياس", [("index.html", "الاستهلاك", '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'),
                    ("sessions.html", "الأدوار والجلسات", '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M17 11a3 3 0 1 0 0-6M21 20c0-2.5-1.6-4.6-4-5.5"/>'),
                    ("hourly.html", "الجلسات بالساعة", '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>')]),
       ("التهيئة", [("skills.html", "حصر المهارات", '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>')])]
ACTIVE = {"dashboard.html": "index.html", "sessions.html": "sessions.html", "hourly.html": "hourly.html", "skills.html": "skills.html"}


def shell(template):
    """غلاف موحّد لكل صفحات المنصة: رابط تخطٍّ، شريط جانبي مجمَّع، فهرس «في هذه الصفحة» (يبنيه JS)، وبداية main."""
    cur = ACTIVE[template]
    groups = []
    for i, (title, items) in enumerate(NAV):
        links = "".join('<li><a href="%s"%s><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">%s</svg><span>%s</span></a></li>'
                        % (href, ' aria-current="page"' if href == cur else "", icon, label) for href, label, icon in items)
        groups.append('<p class="navgroup" id="ng%d">%s</p><ul aria-labelledby="ng%d">%s</ul>' % (i, title, i, links))
    top = ('<a class="skip" href="#main">تخطَّ إلى المحتوى</a><div class="app"><aside class="side">'
           '<div class="brand">منصّة الاستهلاك<small>Claude Code · بالتوكن</small></div>'
           '<nav class="nav" aria-label="صفحات المنصة">%s</nav>'
           '<nav class="toc" id="toc" aria-label="في هذه الصفحة"><p class="toc-title">في هذه الصفحة</p></nav>'
           '<div class="sidefoot" id="themeslot"></div></aside><main id="main" class="page" tabindex="-1">' % "".join(groups))
    return top, "</main></div>"


def render(template, data, parts):
    """يملأ قالبًا: __CSS__ و__LIB__ من الملفات المشتركة، و__DATA__ من data، وباقي العلامات من parts. كل علامة مرة واحدة."""
    css, lib = assets()
    page = (SRC / template).read_text(encoding="utf-8")
    head = (SRC / "ui_theme_head.js").read_text(encoding="utf-8")  # يطبّق السمة المحفوظة قبل الرسم فلا وميض
    assert "<head>" in page
    page = page.replace("<head>", "<head><script>" + head.strip() + "</script>", 1)
    top, bottom = shell(template)
    for token, value in (("__SHELL_OPEN__", top), ("__SHELL_CLOSE__", bottom), ("__CSS__", css), ("__LIB__", lib), *parts.items(), ("__DATA__", embed_json(data))):
        assert token in page, token
        page = page.replace(token, value, 1)
    return page


def write(path, page):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(page)
    os.replace(tmp, path)
