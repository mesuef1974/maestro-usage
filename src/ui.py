"""أجزاء مشتركة بين صفحات المنصة الذاتية: الأسلوب المركزي، ودوال JS للرسم، والغلاف، وتهريب JSON، والكتابة الذرّية.
قالب واحد يخدم عدّة صفحات: تُحذف منه الأقسام التي لا تذكرها الصفحة في سجلّ `pages.py` (علامتا `<!--@sec اسم-->` و`<!--@/sec-->`)."""
import hashlib
import html
import json
import os
import re
import shutil
from pathlib import Path

import pages

SRC = Path(__file__).resolve().parent
CSS_DIR = SRC / "css"
FONT_DIR = SRC / "fonts"
ASSET_URL = "assets/platform.css"
PRELOAD_FONTS = ("IBMPlexSansArabic-Regular", "Cairo", "Inter")  # تُحمَّل مبكرًا لئلا يرمش النص عند الانتقال بين الصفحات
VIEW_MARK = "<!--view %s-->"
SEC_RE = re.compile(r"<!--@sec (\w+)-->(.*?)<!--@/sec-->", re.S)

# علامة «ميزان» (هوية v3 من سِمة، قرار المالك 2026-11-24): «إبرة متصلة»، تنساب الحافة العليا المائلة للتميمة إلى إبرة القياس.
# مسار واحد بلون واحد (لا لون تمييز للرمز)؛ الشعار يأخذ لون العلامة من التوكنات، والأيقونة لونًا ثابتًا لأنها صورة مستقلة.
_MARK = ("M24 58C26 48 32 44 40 42L88 32C100 29.5 112 24 121.6 11.2A8 8 0 0 1 134.4 20.8L120 40C117.6 43.2 118.4 44 122.4 45.6"
         "C130.4 48.8 134.4 52.4 136 58H144A8 8 0 0 1 152 66V74A8 8 0 0 1 144 82H136V88C136 96 132 102 124 102V112A8 8 0 0 1 116 120"
         "H108A8 8 0 0 1 100 112V102H64V112A8 8 0 0 1 56 120H48A8 8 0 0 1 40 112V102C30 102 24 96 24 88V82H16A8 8 0 0 1 8 74V66"
         "A8 8 0 0 1 16 58ZM51 64A8 8 0 0 1 67 64V76A8 8 0 0 1 51 76ZM97 64A8 8 0 0 1 113 64V76A8 8 0 0 1 97 76Z")
_MASCOT = '<path transform="translate(0 16)" fill-rule="evenodd" fill="%(b)s" d="%(d)s"/>'
LOGO = '<svg viewBox="0 0 160 160" aria-hidden="true" focusable="false">%s</svg>' % (_MASCOT % dict(b="var(--brand)", d=_MARK))
FAVICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160"><rect width="160" height="160" fill="#ffffff"/><g transform="translate(8 7) scale(.9)">%s</g></svg>' % (_MASCOT % dict(b="#a8541a", d=_MARK))
FAVICON_LINK = '<link rel="icon" href="data:image/svg+xml,%s">' % FAVICON.replace("<", "%3C").replace(">", "%3E").replace("#", "%23").replace('"', "'")
APPLE_ICON_LINK = '<link rel="apple-touch-icon" href="data:image/png;base64,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">'


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


LIB_MARK = "/*@@PAGE_STATE@@*/"


def lib_js():
    return (SRC / "ui_common.js").read_text(encoding="utf-8")


def lib_split():
    """(المشترك، الخاص بالجزء): المشترك يسبق العلامة ويُضمَّن مرة واحدة في الصفحة؛ ما بعدها يعتمد على حالة الجزء فيبقى داخله."""
    s = lib_js()
    i = s.index(LIB_MARK)
    return s[:i], s[i:]


def embed_json(data):
    """JSON للتضمين داخل script: يُهرَّب منه '</' وفاصلا الأسطر كي لا يُغلق الوسم ولا يتصدّع النص."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def nav_html():
    """الشريط الجانبي: رابط لكل قسم من الصفحة الواحدة (الإبراز عند التمرير يتولاه rail.js)."""
    by_id = {sid: (title, icon) for sid, title, icon in pages.SECTIONS}

    def link(sid):
        title, icon = by_id[sid]
        badge = '<b class="navbadge" id="navBadge-%s" hidden></b>' % sid if sid == "today" else ""
        return ('<li><a href="#%s"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">%s</svg><span>%s</span>%s</a></li>'
                % (sid, pages.ICON[icon], html.escape(title), badge))

    groups = "".join(('<p class="navgroup">%s</p>' % html.escape(label) if label else "") + "<ul>%s</ul>" % "".join(link(s) for s in ids)
                     for label, ids in pages.NAV_GROUPS)
    # «طلب جديد» أول الشريط: لاصق في الحالين (عمود جانبي ≥1024px وشريط علوي أدناه)، والاستمارة تركّز العنوان
    new = ('<a class="newreq" id="newreq" href="#new"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 5v14M5 12h14"/></svg>'
           '<span>طلب جديد</span></a>')
    return new + groups


def shell(cur=None):
    """غلاف الصفحة: رابط تخطٍّ، شريط جانبي بعلامة «ميزان» وروابط الأقسام، وبداية main."""
    top = ('<a class="skip" href="#main">تخطَّ إلى المحتوى</a><div class="app"><aside class="side">'
           '<a class="brand" href="#today" aria-label="ميزان، شاشة اليوم">%s<span><b>ميزان</b><small>القياس والأتمتة</small></span></a>'
           '<nav class="nav" aria-label="أقسام الصفحة">%s</nav>'
           '<div class="sidefoot" id="themeslot"></div></aside><main id="main" class="page" tabindex="-1">' % (LOGO, nav_html()))
    return top, "</main></div>"


HERO = ('<section class="hero" id="hero" aria-label="الأرقام الثلاثة">'
        '<div class="htile"><div class="l">الحصة الأسبوعية الآن</div><div class="v" id="hero-pct">—</div><div class="d" id="hero-pct-d">بانتظار لقطة</div></div>'
        '<div class="htile"><div class="l">متى تنفد؟</div><div class="v" id="hero-full">—</div><div class="d" id="hero-full-d">بانتظار التقدير</div></div>'
        '<div class="htile"><div class="l">المشغّل</div><div class="v" id="hero-run">—</div><div class="d" id="hero-run-d">بانتظار الدفتر</div></div>'
        '</section>')


def pagehead(title, lede, stamp="", hero=False):
    """رأس الصفحة؛ hero يضيف شريط الأرقام الثلاثة (تملؤه أجزاء الصفحة: الحصة من جزء main والمشغّل من جزء runner)."""
    live = ('<div class="live"><button type="button" id="refresh" class="refresh">تحديث فوري</button>'
            '<span id="age" class="sub"></span><span id="health" class="sub" role="status"></span><span id="rmsg" class="sub" role="status"></span>'
            '<span id="gen" hidden>%s</span></div>' % html.escape(stamp))
    return '<header class="pagehead" id="top"><h1>%s</h1><p class="lede">%s</p>%s%s</header>' % (html.escape(title), html.escape(lede), live, HERO if hero else "")


def section_head(sid):
    return '<h2 class="gh" id="%s">%s</h2>' % (sid, html.escape(pages.SECTION_TITLE[sid]))


def select_sections(page_html, wanted):
    """يُبقي من القالب الأقسام المطلوبة بترتيب `wanted`، ويتحقّق أن كل اسم موجود؛ الاسم @معرّف يولّد عنوان قسم الصفحة."""
    found = dict(SEC_RE.findall(page_html))
    first, last = page_html.index("__SHELL_OPEN__") + len("__SHELL_OPEN__"), page_html.index("__SHELL_CLOSE__")
    def piece(n):
        if n.startswith("~"):
            return VIEW_MARK % n[1:]
        return VIEW_MARK % n[1:] + section_head(n[1:]) if n.startswith("@") else found[n]  # KeyError = اسم قسم غير موجود في القالب

    body = "".join(piece(n) for n in wanted)
    return page_html[:first] + "\n" + body + "\n" + page_html[last:]


def render(part, data, parts):
    """يبني جزءًا من الصفحة الواحدة من سجلّه: القالب ثم تصفية الأقسام ثم الرموز (__LIB__ و__DATA__ وparts). تجمعه onepage في الصفحة."""
    page = pages.BY_FILE[part]
    html_ = (SRC / page["template"]).read_text(encoding="utf-8")
    html_ = select_sections(html_, page["sections"])
    data = pages.pack_data(pages.prune_data(data, page["template"], page["sections"]), page["template"])
    top, bottom = shell()
    for token, value in (("__SHELL_OPEN__", top), ("__SHELL_CLOSE__", bottom), ("__LIB__", lib_js()), *parts.items(), ("__DATA__", embed_json(data))):
        if token in ("__STATIC__", "__STAMP__") and token not in html_:
            continue  # قسم هذا الجزء ليس في هذه الصفحة
        assert token in html_, token
        html_ = html_.replace(token, value, 1)
    return html_


def write(path, page):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(page)
    os.replace(tmp, path)
