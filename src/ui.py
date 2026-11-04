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


def nav_html():
    """الشريط الجانبي: رابط لكل قسم من الصفحة الواحدة (الإبراز عند التمرير يتولاه rail.js)."""
    links = "".join('<li><a href="#%s"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">%s</svg><span>%s</span></a></li>'
                    % (sid, pages.ICON[icon], html.escape(title)) for sid, title, icon in pages.SECTIONS)
    return '<ul>%s</ul>' % links


def shell(cur=None):
    """غلاف الصفحة: رابط تخطٍّ، شريط جانبي بعلامة «ميزان» وروابط الأقسام، وبداية main."""
    top = ('<a class="skip" href="#main">تخطَّ إلى المحتوى</a><div class="app"><aside class="side">'
           '<a class="brand" href="#top" aria-label="ميزان، أعلى الصفحة">%s<span><b>ميزان</b><small>استهلاك Claude Code بالتوكن</small></span></a>'
           '<nav class="nav" aria-label="أقسام الصفحة">%s</nav>'
           '<div class="sidefoot" id="themeslot"></div></aside><main id="main" class="page" tabindex="-1">' % (LOGO, nav_html()))
    return top, "</main></div>"


def pagehead(title, lede, stamp=""):
    live = ('<div class="live"><button type="button" id="refresh" class="refresh">تحديث فوري</button>'
            '<span id="age" class="sub"></span><span id="rmsg" class="sub" role="status"></span><span id="gen" hidden>%s</span></div>' % html.escape(stamp))
    return '<header class="pagehead" id="top"><h1>%s</h1><p class="lede">%s</p>%s</header>' % (html.escape(title), html.escape(lede), live)


def section_head(sid):
    return '<h2 class="gh" id="%s">%s</h2>' % (sid, html.escape(pages.SECTION_TITLE[sid]))


def select_sections(page_html, wanted):
    """يُبقي من القالب الأقسام المطلوبة بترتيب `wanted`، ويتحقّق أن كل اسم موجود؛ الاسم @معرّف يولّد عنوان قسم الصفحة."""
    found = dict(SEC_RE.findall(page_html))
    first, last = page_html.index("__SHELL_OPEN__") + len("__SHELL_OPEN__"), page_html.index("__SHELL_CLOSE__")
    body = "".join(section_head(n[1:]) if n.startswith("@") else found[n] for n in wanted)  # KeyError = اسم قسم غير موجود في القالب
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
