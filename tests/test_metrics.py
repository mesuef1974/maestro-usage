"""سجلّ المقاييس: مفاتيح فريدة، وكل صفحة فيها قسم التعريفات تأخذ تعريفاتها من السجلّ، ولا فراغ __DEFS__ يبقى في الصفحات المبنية."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import metrics  # noqa: E402
import pages  # noqa: E402
import skills_page  # noqa: E402


class TestMetrics(unittest.TestCase):
    def test_keys_unique_and_pages_exist(self):
        keys = [m["key"] for m in metrics.METRICS]
        self.assertEqual(len(keys), len(set(keys)))
        for m in metrics.METRICS:
            self.assertTrue(m["pages"], m["key"])
            for f in m["pages"]:
                self.assertIn(f, pages.BY_FILE, (m["key"], f))
                self.assertIn("defs", pages.BY_FILE[f]["sections"], (m["key"], f))  # لا تعريف لصفحة بلا قسم تعريفات

    def test_every_defs_page_has_definitions(self):
        for p in pages.PAGES:
            if "defs" in p["sections"]:
                self.assertGreaterEqual(len(metrics.for_page(p["file"])), 2, p["file"])
        self.assertIn("quota_cost", [m["key"] for m in metrics.for_page("index.html")])

    def test_defs_html_escapes_meta_and_keeps_fill_slots(self):
        h = metrics.defs_html("roles.html")
        self.assertIn('data-fill="threshold"', h)
        self.assertIn('<span class="mu">توكن · usage_turns · الفترة المحدّدة</span>', h)
        self.assertNotIn("__DEFS__", h)

    def test_rendered_page_has_registry_defs(self):
        page = skills_page.render(skills_page.payload(dict(files=0, scanned_at=None, usage={})), "2026-10-30 12:00", "skills.html")
        self.assertNotIn("__DEFS__", page)
        self.assertIn('data-fill="cpt"', page)
        self.assertIn("استعمال المهارة", page)


if __name__ == "__main__":
    unittest.main()
