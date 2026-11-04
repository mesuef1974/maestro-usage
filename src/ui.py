"""أجزاء مشتركة بين صفحات المنصة الذاتية: الأسلوب المركزي، ودوال JS للرسم، والغلاف، وتهريب JSON، والكتابة الذرّية.
قالب واحد يخدم عدّة صفحات: تُحذف منه الأقسام التي لا تذكرها الصفحة في سجلّ `pages.py` (علامتا `<!--@sec اسم-->` و`<!--@/sec-->`)."""
import hashlib
import html
import json
import os
import re
import shutil
from pathlib import Path

import metrics
import pages

SRC = Path(__file__).resolve().parent
CSS_DIR = SRC / "css"
FONT_DIR = SRC / "fonts"
ASSET_URL = "assets/platform.css"
PRELOAD_FONTS = ("NotoNaskhArabic", "NotoKufiArabic", "Inter")  # تُحمَّل مبكرًا لئلا يرمش النص عند الانتقال بين الصفحات
SEC_RE = re.compile(r"<!--@sec (\w+)-->(.*?)<!--@/sec-->", re.S)

# علامة «ميزان»: تميمة مبنية بالبكسل (أصلية، مستوحاة من فكرة تميمة المساعد لا نسخة منها): جسم نحاسي بعينين وذراعين وأربع أرجل،
# وإبرة صغيرة فوق الرأس ترمز إلى المقياس. الألوان من توكنات الهوية؛ نسخة الأيقونة تحمل ألوانًا ثابتة لأنها صورة مستقلة.
_MASCOT = ('<path d="M16 9L21 3" stroke="%(a)s" stroke-width="2.4" stroke-linecap="round" fill="none"/>'
           '<rect x="4" y="9" width="24" height="14" rx="2.5" fill="%(b)s"/>'
           '<rect x="1" y="13" width="4" height="5" rx="1" fill="%(b)s"/><rect x="27" y="13" width="4" height="5" rx="1" fill="%(b)s"/>'
           '<rect x="8" y="23" width="4" height="5" rx="1" fill="%(b)s"/><rect x="20" y="23" width="4" height="5" rx="1" fill="%(b)s"/>'
           '<rect x="10" y="13" width="2.6" height="5" rx="1.3" fill="%(e)s"/><rect x="19.4" y="13" width="2.6" height="5" rx="1.3" fill="%(e)s"/>')
LOGO = '<svg viewBox="0 0 32 32" aria-hidden="true" focusable="false">%s</svg>' % (_MASCOT % dict(b="var(--brand)", a="var(--accent)", e="var(--surface)"))
FAVICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#f6f3ee"/>%s</svg>' % (_MASCOT % dict(b="#a8541a", a="#9a6b00", e="#f6f3ee"))
FAVICON_LINK = '<link rel="icon" href="data:image/svg+xml,%s">' % FAVICON.replace("<", "%3C").replace(">", "%3E").replace("#", "%23").replace('"', "'")


def css_text():
    """الأسلوب المركزي: ملفات src/css بترتيب أسمائها (توكنات ثم أساس ثم غلاف ثم مكوّنات ثم بيانات ثم صفحات ثم استجابة)."""
    return "\n".join((p.read_text(encoding="utf-8")) for p in sorted(CSS_DIR.glob("*.css")))


def css_hash():
    return hashlib.sha256(css_text().encode("utf-8")).hexdigest()[:10]


def write_assets(out_dir):
    """يكتب platform.css في out_dir/assets (ذرّيًّا) ويعيد مساره."""
    d = Path(out_dir) / "assets"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "platform.css"
    write(str(path), css_text())
    fonts = d / "fonts"
    fonts.mkdir(exist_ok=True)
    for f in FONT_DIR.glob("*"):  # الخطوط ونصوص ترخيصها (OFL) بجانب الأسلوب
        if f.suffix in (".ttf", ".txt") and not (fonts / f.name).exists():
            shutil.copyfile(f, fonts / f.name)
    return path


def lib_js():
    return (SRC / "ui_common.js").read_text(encoding="utf-8")


def embed_json(data):
    """JSON للتضمين داخل script: يُهرَّب منه '</' وفاصلا الأسطر كي لا يُغلق الوسم ولا يتصدّع النص."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def nav_html(cur):
    """الشريط الجانبي من السجلّ: مجموعات فصفحات، والصفحة الحالية بـ aria-current."""
    out = []
    for i, g in enumerate(pages.GROUPS):
        items = [p for p in pages.PAGES if p["group"] == g]
        if not items:
            continue
        links = "".join('<li><a href="%s"%s><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">%s</svg><span>%s</span></a></li>'
                        % (p["file"], ' aria-current="page"' if p["file"] == cur else "", pages.ICON[p["icon"]], html.escape(p["title"]))
                        for p in items)
        out.append('<p class="navgroup" id="ng%d">%s</p><ul aria-labelledby="ng%d">%s</ul>' % (i, g, i, links))
    return "".join(out)


def shell(cur):
    """غلاف موحّد: رابط تخطٍّ، شريط جانبي بعلامة «ميزان» وتنقّل مجمَّع، وبداية main."""
    top = ('<a class="skip" href="#main">تخطَّ إلى المحتوى</a><div class="app"><aside class="side">'
           '<a class="brand" href="index.html" aria-label="ميزان، الصفحة الرئيسية">%s<span><b>ميزان</b><small>استهلاك Claude Code بالتوكن</small></span></a>'
           '<nav class="nav" aria-label="صفحات المنصة">%s</nav>'
           '<div class="sidefoot" id="themeslot"></div></aside><main id="main" class="page" tabindex="-1">' % (LOGO, nav_html(cur)))
    return top, "</main></div>"


def pagehead(page, template, stamp=""):
    live = ""
    if template in pages.LIVE_TEMPLATES:
        live = ('<div class="live"><button type="button" id="refresh" class="refresh">تحديث فوري</button>'
                '<span id="age" class="sub"></span><span id="rmsg" class="sub" role="status"></span><span id="gen" hidden>%s</span></div>' % html.escape(stamp))
    return '<header class="pagehead"><h1>%s</h1><p class="lede">%s</p>%s</header>' % (html.escape(page["title"]), html.escape(page["lede"]), live)


def hub_html():
    """دليل الصفحات في «نظرة عامة»: مجموعات وبطاقة لكل صفحة بعنوانها وسطرها التمهيدي."""
    out = []
    for g in pages.GROUPS:
        items = [p for p in pages.PAGES if p["group"] == g and p["file"] != "index.html"]
        if items:
            lis = "".join('<li><a href="%s"><b>%s</b><span>%s</span></a></li>' % (p["file"], html.escape(p["title"]), html.escape(p["lede"])) for p in items)
            out.append('<section class="hubgroup" aria-labelledby="hub%d"><h2 id="hub%d">%s</h2><ul>%s</ul></section>' % (len(out), len(out), g, lis))
    return '<div class="hub">%s</div>' % "".join(out)


def select_sections(page_html, wanted):
    """يُبقي من القالب الأقسام المطلوبة بترتيب `wanted` (والمركّب `hub` يُولَّد)، ويتحقّق أن كل اسم موجود."""
    found = dict(SEC_RE.findall(page_html))
    first, last = page_html.index("__PAGEHEAD__") + len("__PAGEHEAD__"), page_html.index("__SHELL_CLOSE__")
    body = "".join(hub_html() if n == "hub" else found[n] for n in wanted)  # KeyError = اسم قسم غير موجود في القالب
    return page_html[:first] + "\n" + body + "\n" + page_html[last:]


def render(page_file, data, parts):
    """يبني صفحة من سجلّها: القالب ثم تصفية الأقسام ثم __ASSETS__ و__PAGEHEAD__ والغلاف و__LIB__ و__DATA__ وparts (ما وُجد منها)."""
    page = pages.BY_FILE[page_file]
    html_ = (SRC / page["template"]).read_text(encoding="utf-8")
    html_ = select_sections(html_, page["sections"])
    data = pages.pack_data(pages.prune_data(data, page["template"], page["sections"]), page["template"])
    head = (SRC / "ui_theme_head.js").read_text(encoding="utf-8")  # يطبّق السمة المحفوظة قبل الرسم فلا وميض
    assert "<head>" in html_
    html_ = html_.replace("<head>", "<head><script>" + head.strip() + "</script>", 1)
    html_ = re.sub(r"<title>.*?</title>", "<title>%s · ميزان</title>" % html.escape(page["title"]), html_, count=1)
    if page_file == "plan.html":  # رابط الصفحة إلى نفسها بلا معنى
        html_ = re.sub(r'<a href="plan.html">[^<]*</a>', "", html_)
    top, bottom = shell(page_file)
    preload = "".join('<link rel="preload" as="font" type="font/ttf" crossorigin href="assets/fonts/%s.ttf">' % f for f in PRELOAD_FONTS)
    assets = FAVICON_LINK + preload + '<link rel="stylesheet" href="%s?v=%s">' % (ASSET_URL, css_hash())
    for token, value in (("__ASSETS__", assets), ("__PAGEHEAD__", pagehead(page, page["template"], parts.get("__STAMP__", ""))), ("__SHELL_OPEN__", top), ("__SHELL_CLOSE__", bottom),
                         ("__LIB__", lib_js()), ("__DEFS__", metrics.defs_html(page_file)), *parts.items(), ("__DATA__", embed_json(data))):
        if token in ("__STATIC__", "__STAMP__", "__DEFS__") and token not in html_:
            continue  # قسم هذا الجزء ليس في هذه الصفحة
        assert token in html_, token
        html_ = html_.replace(token, value, 1)
    return html_


def write(path, page):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(page)
    os.replace(tmp, path)
