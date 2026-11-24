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
FAVICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160"><rect width="160" height="160" rx="32" fill="#f6f3ee"/><g transform="translate(16 16) scale(.8)">%s</g></svg>' % (_MASCOT % dict(b="#a8541a", d=_MARK))
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
