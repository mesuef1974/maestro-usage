"""غلاف المنصة الموحّد وسجلّ الصفحات: كل قالب يستعمل الغلاف، والتنقّل من السجلّ، وتصفية الأقسام، والأسلوب المركزي."""
import os
import re
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import pages  # noqa: E402
import skills_page  # noqa: E402
import ui  # noqa: E402

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


def template_sections(name):
    return re.findall(r"<!--@sec (\w+)-->", open(os.path.join(SRC, name), encoding="utf-8").read())


class UiShellTest(unittest.TestCase):
    def test_templates_use_shell(self):
        for name in {p["template"] for p in pages.PAGES}:
            s = open(os.path.join(SRC, name), encoding="utf-8").read()
            for token in ("__SHELL_OPEN__", "__SHELL_CLOSE__", "__PAGEHEAD__", "__ASSETS__"):
                self.assertEqual(s.count(token), 1, (name, token))
            self.assertNotIn("<style", s, name)  # الأسلوب مركزي في src/css لا في القوالب
            self.assertNotIn('<nav class="nav"', s, name)  # لا تنقّل مكتوب يدويًّا
            self.assertEqual(s.count("<!--@sec "), s.count("<!--@/sec-->"), name)
            self.assertEqual(len(re.findall(r"<h1[ >]", s)), 0, name)  # العنوان من السجلّ عبر __PAGEHEAD__

    def test_refresh_button_handles_busy_cycle(self):
        """زر التحديث: جواب busy لا يعيد تحميل صفحة قديمة، ورسالة بعد 15 ثانية تشرح الانتظار."""
        s = open(os.path.join(SRC, "ui_common.js"), encoding="utf-8").read()
        for token in ("j.busy", "setTimeout(function(){msg.textContent=", "clearTimeout(slow)", "if(j&&j.ok)location.reload()"):
            self.assertIn(token, s)

    def test_registry_is_consistent(self):
        files = [p["file"] for p in pages.PAGES]
        self.assertEqual(len(files), len(set(files)))
        self.assertGreaterEqual(len(files), 12)
        self.assertIn("index.html", files)
        for p in pages.PAGES:
            self.assertIn(p["group"], pages.GROUPS, p["file"])
            self.assertIn(p["icon"], pages.ICON, p["file"])
            known = set(template_sections(p["template"])) | {"hub"}
            for sec in p["sections"]:
                self.assertIn(sec, known, (p["file"], sec))

    def test_every_template_section_is_used_by_some_page(self):
        for t in {p["template"] for p in pages.PAGES}:
            used = {s for p in pages.for_template(t) for s in p["sections"]}
            self.assertEqual(set(template_sections(t)) - used, set(), t)

    def test_shell_marks_current_page_only(self):
        for p in pages.PAGES:
            top, bottom = ui.shell(p["file"])
            self.assertEqual(top.count('aria-current="page"'), 1, p["file"])
            self.assertIn('href="%s" aria-current="page"' % p["file"], top)
            self.assertIn('id="main"', top)
            self.assertIn('class="skip" href="#main"', top)
            self.assertNotIn('id="toc"', top)  # لا فهرس «في هذه الصفحة»
            self.assertEqual(bottom, "</main></div>")

    def test_nav_lists_every_page_once(self):
        top, _ = ui.shell("index.html")
        hrefs = re.findall(r'<li><a href="([^"]+)"', top)
        self.assertEqual(sorted(hrefs), sorted(p["file"] for p in pages.PAGES))

    def test_render_keeps_only_page_sections(self):
        page = skills_page.render(skills_page.payload(dict(files=0, scanned_at=None, usage={})), "2026-10-30 12:00", "skills.html")
        self.assertNotIn("__SHELL_", page)
        self.assertNotIn("<!--@", page)
        self.assertEqual(page.count("<h1>"), 1)
        self.assertIn('<main id="main"', page)
        self.assertIn('href="assets/platform.css?v=%s"' % ui.css_hash(), page)

    def test_central_css_build(self):
        with tempfile.TemporaryDirectory() as d:
            path = ui.write_assets(d)
            css = re.sub(r"/\*.*?\*/", "", open(path, encoding="utf-8").read(), flags=re.S)  # بلا التعليقات
            self.assertIn("--brand:", css)
            self.assertLess(css.index("--brand:"), css.index(".app{"))  # التوكنات قبل الغلاف
            for f in ("NotoKufiArabic.ttf", "NotoNaskhArabic.ttf", "Inter.ttf"):  # الخطوط تُنسخ بجانب الأسلوب ويشير إليها @font-face
                self.assertTrue((Path(d) / "assets" / "fonts" / f).is_file(), f)
                self.assertIn("fonts/" + f, css)
        self.assertNotIn("letter-spacing", css)

    def test_component_css_uses_tokens_not_literal_colors(self):
        for name in sorted(os.listdir(ui.CSS_DIR)):
            if name.startswith("00-"):
                continue
            css = open(os.path.join(ui.CSS_DIR, name), encoding="utf-8").read()
            css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
            literals = re.findall(r"#[0-9a-fA-F]{3,8}", css)
            self.assertLessEqual(len(literals), 4, (name, literals))  # الألوان من التوكنات؛ يُسمح بحفنة (ظلّ وطباعة)



class TestPayloadSlimming(unittest.TestCase):
    def test_prune_empties_unneeded_keys_by_section(self):
        data = {"models": ["m"], "a": [{"x": 1}], "b": [{"y": 1}], "sessions": {"1": {}}, "plan": [{"t": 1}], "threshold": 3}
        got = pages.prune_data(data, "dashboard.html", ["filters", "h4"])
        self.assertEqual((got["a"], got["plan"]), ([], []))
        self.assertEqual(got["b"], [{"y": 1}])
        self.assertEqual(got["models"], ["m"])
        got = pages.prune_data(data, "dashboard.html", ["h1"])
        self.assertEqual((got["b"], got["sessions"]), ([], {}))
        self.assertIs(pages.prune_data(data, "skills.html", ["tbl"]), data)  # قالب بلا خريطة حاجات يبقى كاملًا

    def test_pack_data_columnar_roundtrip_shape(self):
        rows = [{"s": i, "d": "2026-10-01", "t": i * 2} for i in range(30)]
        got = pages.pack_data({"c": rows, "x": [1]}, "sessions.html")
        self.assertEqual(got["c"]["$cols"], ["s", "d", "t"])
        self.assertEqual(got["c"]["rows"][3], [3, "2026-10-01", 6])
        self.assertEqual(got["x"], [1])
        ragged = rows[:-1] + [{"s": 1}]
        self.assertEqual(pages.pack_data({"c": ragged}, "sessions.html")["c"], ragged)  # صفوف غير منتظمة لا تُعبّأ

if __name__ == "__main__":
    unittest.main()
