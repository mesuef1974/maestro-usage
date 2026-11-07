"""غلاف الصفحة الواحدة وسجلّ أجزائها: كل قالب يستعمل الغلاف، والتنقّل من أقسام السجلّ، وتصفية الأقسام، والأسلوب المركزي."""
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
            for token in ("__SHELL_OPEN__", "__SHELL_CLOSE__"):
                self.assertEqual(s.count(token), 1, (name, token))
            self.assertNotIn("<style", s, name)  # الأسلوب مركزي في src/css لا في القوالب
            self.assertNotIn('<nav class="nav"', s, name)  # لا تنقّل مكتوب يدويًّا
            self.assertEqual(s.count("<!--@sec "), s.count("<!--@/sec-->"), name)
            self.assertEqual(len(re.findall(r"<h1[ >]", s)), 0, name)  # العنوان يكتبه onepage مرة واحدة

    def test_refresh_button_handles_busy_cycle(self):
        """زر التحديث: جواب busy لا يعيد تحميل صفحة قديمة، ورسالة بعد 15 ثانية تشرح الانتظار."""
        s = open(os.path.join(SRC, "ui_common.js"), encoding="utf-8").read()
        for token in ("j.busy", "setTimeout(function(){msg.textContent=", "clearTimeout(slow)", "if(j&&j.ok)location.reload()"):
            self.assertIn(token, s)

    def test_registry_is_consistent(self):
        files = [p["file"] for p in pages.PAGES]
        self.assertEqual(len(files), len(set(files)))
        for p in pages.PAGES:
            known = set(template_sections(p["template"]))
            for sec in p["sections"]:
                if sec[0] in "@~":
                    self.assertIn(sec[1:], pages.SECTION_TITLE, (p["file"], sec))
                else:
                    self.assertIn(sec, known, (p["file"], sec))
        for _sid, _title, icon in pages.SECTIONS:
            self.assertIn(icon, pages.ICON)
        headed = [s[1:] for p in pages.PAGES for s in p["sections"] if s.startswith("@")]
        self.assertEqual(sorted(headed), sorted(pages.SECTION_TITLE))  # كل شاشة لها عنوان واحد
        self.assertEqual([s for _label, ids in pages.NAV_GROUPS for s in ids], [sid for sid, _t, _i in pages.SECTIONS])

    def test_every_template_section_is_used_by_some_part(self):
        for t in {p["template"] for p in pages.PAGES}:
            used = {s for p in pages.PAGES if p["template"] == t for s in p["sections"]}
            self.assertEqual(set(template_sections(t)) - used, set(), t)

    def test_shell_nav_links_every_section_once(self):
        top, bottom = ui.shell()
        hrefs = re.findall(r'<li><a href="#([^"]+)"', top)
        self.assertEqual(hrefs, [sid for sid, _t, _i in pages.SECTIONS])
        self.assertIn('id="main"', top)
        self.assertIn('class="skip" href="#main"', top)
        self.assertEqual(bottom, "</main></div>")

    def test_render_keeps_only_part_sections(self):
        page = ui.render("skills", skills_page.payload(dict(files=0, scanned_at=None, usage={})), {"__STAMP__": "2026-10-30 12:00"})
        self.assertNotIn("__SHELL_", page)
        self.assertNotIn("<!--@", page)
        self.assertIn('<h2 class="gh" id="skills">', page)
        self.assertIn('<main id="main"', page)

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
        data = {"models": ["m"], "a": [{"x": 1}], "plan": [{"t": 1}], "changes": [{"c": 1}], "threshold": 3}
        got = pages.prune_data(data, "dashboard.html", ["h1"])
        self.assertEqual((got["plan"], got["changes"]), ([], []))
        self.assertEqual((got["a"], got["models"]), ([{"x": 1}], ["m"]))
        got = pages.prune_data(data, "dashboard.html", ["h3"])
        self.assertEqual((got["a"], got["plan"]), ([], [{"t": 1}]))
        self.assertIs(pages.prune_data(data, "skills.html", ["tbl"]), data)  # قالب بلا خريطة حاجات يبقى كاملًا

    def test_pack_data_columnar_roundtrip_shape(self):
        rows = [{"s": i, "d": "2026-10-01", "t": i * 2} for i in range(30)]
        got = pages.pack_data({"a": rows, "x": [1]}, "dashboard.html")
        self.assertEqual(got["a"]["$cols"], ["s", "d", "t"])
        self.assertEqual(got["a"]["rows"][3], [3, "2026-10-01", 6])
        self.assertEqual(got["x"], [1])
        ragged = rows[:-1] + [{"s": 1}]
        self.assertEqual(pages.pack_data({"a": ragged}, "dashboard.html")["a"], ragged)  # صفوف غير منتظمة لا تُعبّأ


if __name__ == "__main__":
    unittest.main()
