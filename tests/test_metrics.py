"""سجلّ المقاييس: مفاتيح فريدة، وكل صفحة فيها قسم التعريفات تأخذ تعريفاتها من السجلّ، ولا فراغ __DEFS__ يبقى في الصفحات المبنية."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import metrics  # noqa: E402
import ui  # noqa: E402
import skills_page  # noqa: E402


class TestMetrics(unittest.TestCase):
    def test_keys_unique_and_every_metric_has_fields(self):
        keys = [m["key"] for m in metrics.METRICS]
        self.assertEqual(len(keys), len(set(keys)))
        for m in metrics.METRICS:
            for f in ("name", "unit", "source", "window", "definition"):
                self.assertTrue(m[f], (m["key"], f))

    def test_defs_html_escapes_meta_and_keeps_fill_slots(self):
        h = metrics.defs_html()
        self.assertIn('data-fill="threshold"', h)
        self.assertIn('<span class="mu">توكن · usage_turns · الفترة المحدّدة</span>', h)
        self.assertNotIn("__DEFS__", h)

    def test_onepage_has_registry_defs(self):
        import onepage
        page = onepage.build([("skills", ui.render("skills", skills_page.payload(dict(files=0, scanned_at=None, usage={})), {"__STAMP__": "x"}), False)], "2026-10-30 12:00")
        self.assertNotIn("__DEFS__", page)
        self.assertIn("استعمال المهارة", page)


if __name__ == "__main__":
    unittest.main()
