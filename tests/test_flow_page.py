"""صفحة رسم الأتمتة: سلامة قائمة المراحل والروابط (مراجع صحيحة، أرقام متسلسلة، مسارات معروفة) وبناء الصفحة من القالب."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import flow_page  # noqa: E402
import pages  # noqa: E402


class FlowPageTest(unittest.TestCase):
    def test_graph_is_consistent(self):
        f = flow_page.payload()["flow"]
        ids = {n["id"] for n in f["nodes"]}
        lanes = {ln["k"] for ln in f["lanes"]}
        kinds = {k["k"] for k in f["kinds"]}
        self.assertEqual(len(ids), len(f["nodes"]))  # لا معرّف مكرّر
        self.assertEqual(sorted(n["n"] for n in f["nodes"]), list(range(1, len(f["nodes"]) + 1)))  # الأرقام متسلسلة
        for n in f["nodes"]:
            self.assertIn(n["lane"], lanes, n["id"])
            self.assertIn(n["kind"], kinds, n["id"])
            self.assertLess(n["col"], f["cols"])
        pos = {}
        for n in f["nodes"]:  # لا مرحلتان في الخلية نفسها
            self.assertNotIn((n["lane"], n["col"]), pos, n["id"])
            pos[(n["lane"], n["col"])] = n["id"]
        for e in f["edges"]:
            self.assertIn(e["a"], ids)
            self.assertIn(e["b"], ids)
            self.assertIn(e["kind"], ("plain", "auto", "dash", "bad"))
            self.assertIn(e["route"], ("", "h", "v", "vh", "hv", "hvh", "vhv"))
        self.assertEqual(sum(1 for n in f["nodes"] if n["kind"] == "gate"), 1)  # معاينة المالك الاختيارية: القرار البشري الوحيد
        self.assertEqual(sum(1 for n in f["nodes"] if n["kind"] == "end"), 1)

    def test_render_builds_page_without_db(self):
        html = flow_page.render(flow_page.payload(), "2026-11-03 21:00")
        for s in ('id="fw"', 'id="stages"', "function layout()", "function download()", "المصدر والتحفظات", "رسم الأتمتة · ميزان"):
            self.assertIn(s, html)
        self.assertNotIn("__DEFS__", html)
        self.assertNotIn('id="refresh"', html)  # صفحة ساكنة بلا زرّ التحديث الفوري
        p = pages.BY_FILE["flow.html"]
        self.assertEqual((p["group"], p["sections"]), ("الحوكمة", ["flow", "stages", "source"]))


if __name__ == "__main__":
    unittest.main()
