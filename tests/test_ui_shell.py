"""غلاف المنصة الموحّد: كل قالب يستعمله، والتنقّل متطابق، ورابط التخطّي وmain موجودان، والصفحة الحالية وحدها aria-current."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import skills_page  # noqa: E402
import ui  # noqa: E402

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


class UiShellTest(unittest.TestCase):
    def test_templates_use_shell(self):
        for name in ui.ACTIVE:
            s = open(os.path.join(SRC, name), encoding="utf-8").read()
            self.assertEqual(s.count("__SHELL_OPEN__"), 1, name)
            self.assertEqual(s.count("__SHELL_CLOSE__"), 1, name)
            self.assertNotIn('<nav class="nav"', s, name)  # لا تنقّل مكتوب يدويًّا
            self.assertEqual(len(re.findall(r"<h1[ >]", s)), 1, name)

    def test_shell_marks_current_page_only(self):
        for tpl, cur in ui.ACTIVE.items():
            top, bottom = ui.shell(tpl)
            self.assertEqual(top.count('aria-current="page"'), 1, tpl)
            self.assertIn('href="%s" aria-current="page"' % cur, top)
            self.assertIn('id="main"', top)
            self.assertIn('class="skip" href="#main"', top)
            self.assertIn('id="toc"', top)
            self.assertEqual(bottom, "</main></div>")

    def test_nav_covers_all_pages(self):
        hrefs = [h for _, items in ui.NAV for h, _, _ in items]
        self.assertEqual(sorted(hrefs), sorted(ui.ACTIVE.values()))

    def test_rendered_page_has_no_leftover_tokens(self):
        page = skills_page.render(skills_page.payload(dict(files=0, scanned_at=None, usage={})), "2026-10-30 12:00")
        self.assertNotIn("__SHELL_", page)
        self.assertIn('<main id="main"', page)
        self.assertIn("</main>", page)


if __name__ == "__main__":
    unittest.main()
