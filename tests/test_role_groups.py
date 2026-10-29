"""اختبار تسمية الأدوار: الرقم أولًا، وإلا فئة المجلد للجلسات بلا رقم."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import role_groups as rg  # noqa: E402


class TestRoleGroups(unittest.TestCase):
    def test_number_wins(self):
        self.assertEqual(rg.role_name("0101", "C:\\x\\MonitorWidget"), "0101")
        self.assertEqual(rg.role_name("8094", "D:\\y"), "8094")
        self.assertTrue(rg.is_project("0801"))
        self.assertFalse(rg.is_project("8094"))
        self.assertFalse(rg.is_project(rg.OTHER))

    def test_unnumbered_by_folder(self):
        g = rg.unnumbered_group
        self.assertEqual(g("C:\\Users\\m\\Documents\\Scripts\\MonitorWidget"), rg.PREFIX + "مراقب MonitorWidget")
        self.assertEqual(g("D:\\shschool_mvp"), rg.PREFIX + "مستودع shschool_mvp")
        self.assertEqual(g("C:\\Users\\m\\delivery_manager_work"), rg.PREFIX + "مدير التسليم delivery_manager_work")
        self.assertEqual(g("D:\\shschool_mvp\\.claude\\worktrees\\silly-1"), rg.PREFIX + "أشجار عمل shschool_mvp")
        self.assertEqual(g("D:/other/.claude/worktrees/wt"), rg.OTHER)
        self.assertEqual(g("C:\\Users\\m\\maestro_usage"), rg.OTHER)
        self.assertEqual(g(None), rg.OTHER)
        self.assertEqual(g(""), rg.OTHER)


if __name__ == "__main__":
    unittest.main()
