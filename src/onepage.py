"""الصفحة الواحدة: تجمع أجزاء المنصة (كل جزء قالب بقسمه ونصّه البرمجي ومعطياته) في index.html واحدة.

يُبنى كل جزء بـ`ui.render` ثم تُستخرج منه أقسام main ومعطياته ونصّه، ويُلفّ نصّه في دالة مستقلة ومعرّف معطياته فريد،
فلا تتصادم النسخ. الغلاف والرأس والتعريفات وعنصر التلميح تُكتب هنا مرة واحدة.
"""
import html
import re

import metrics
import ui

TITLE = "ميزان"
LEDE = "الحصة والاستهلاك والمهارات والتخزين والأتمتة في صفحة واحدة."
MAIN_RE = re.compile(r'<main id="main" class="page" tabindex="-1">(.*?)</main>', re.S)
DATA_RE = re.compile(r'<script type="application/json" id="data">(.*?)</script>', re.S)
CODE_RE = re.compile(r"</main></div>\s*(?:<div id=\"tip\"[^>]*></div>\s*)?<script type=\"application/json\" id=\"data\">.*?</script>\s*<script>(.*?)</script>", re.S)
LINK_RE = re.compile(r'<a href="(?:plan|runner|flow|index)\.html">([^<]*)</a>')


def extract(part, page_html, scriptless=False):
    """يعيد (أقسام main، وسم المعطيات، النص البرمجي) لجزء؛ النص والمعطيات فارغان للجزء بلا نص."""
    main = MAIN_RE.search(page_html).group(1)
    main = LINK_RE.sub(lambda m: m.group(1), main)  # روابط الصفحات القديمة صارت أقسامًا في الصفحة نفسها
    if scriptless:
        return main, "", ""
    data = DATA_RE.search(page_html)
    code = CODE_RE.search(page_html)
    assert data and code, part
    tag = '<script type="application/json" id="data-%s">%s</script>' % (part, data.group(1))
    js = code.group(1).replace('getElementById("data")', 'getElementById("data-%s")' % part)
    shared, _ = ui.lib_split()
    assert shared in js, part  # المكتبة المشتركة تُحذف من الجزء وتُضمَّن مرة واحدة في الصفحة (build)
    js = js.replace(shared, "", 1)
    return main, tag, "(function(){\n%s\n})();" % js


def build(parts, stamp):
    """parts: قائمة (المعرّف، HTML الجزء مبنيًّا بـ ui.render، بلا نص؟) بالترتيب. تعيد صفحة index.html كاملة."""
    mains, tags, codes = [], [], []
    for part, page_html, scriptless in parts:
        m, t, c = extract(part, page_html, scriptless)
        mains.append(m)
        tags.append(t)
        codes.append(c)
    top, bottom = ui.shell()
    head = (ui.SRC / "ui_theme_head.js").read_text(encoding="utf-8").strip()
    preload = "".join('<link rel="preload" as="font" type="font/ttf" crossorigin href="assets/fonts/%s.ttf">' % f for f in ui.PRELOAD_FONTS)
    assets = ui.FAVICON_LINK + preload + '<link rel="stylesheet" href="%s?v=%s">' % (ui.ASSET_URL, ui.css_hash())
    defs = '<details class="card defs"><summary>التعريفات والتحفظات</summary>%s</details>' % metrics.defs_html()
    rail = "\n".join((ui.SRC / n).read_text(encoding="utf-8") for n in ("rail.js", "fold.js"))
    shared = ui.lib_split()[0]  # المكتبة المشتركة مرة واحدة قبل الأجزاء (كانت تُضمَّن داخل كل جزء فتضخّم الصفحة)
    return ("<!doctype html>\n<html lang=\"ar\" dir=\"rtl\">\n<head><script>%s</script>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>%s</title>\n%s\n</head>\n<body>\n%s\n%s\n%s\n%s\n"
            "<div id=\"tip\" role=\"status\" aria-live=\"off\"></div>\n%s\n<script>\n%s\n</script>\n<script>\n%s\n</script>\n<script>\n%s\n</script>\n</body>\n</html>\n"
            % (head, html.escape(TITLE), assets, top, ui.pagehead(TITLE, LEDE, stamp, hero=True), "\n".join(mains) + defs, bottom, "\n".join(tags),
               shared, "\n".join(codes), rail))
