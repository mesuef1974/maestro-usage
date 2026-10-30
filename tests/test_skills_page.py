"""صفحة حصر المهارات: الحصر من الملفات، دمج الاستعمال، وسلامة التوصيات والتوليد."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import skill_usage  # noqa: E402
import skills_page  # noqa: E402


class SkillsPageTest(unittest.TestCase):
    def test_curation_values_valid(self):
        for key, (benefit, rec, dups, note) in skills_page.CURATION.items():
            self.assertIn(rec, skills_page.RECS, key)
            self.assertTrue(benefit and note, key)
            self.assertIsInstance(dups, list, key)
        for key, _src, _chars, benefit, rec, dups, note in skills_page.VIRTUAL:
            self.assertIn(rec, skills_page.RECS, key)
            self.assertTrue(benefit and note, key)

    def test_payload_merges_usage(self):
        ud = dict(files=3, scanned_at="2026-10-30T00:00:00Z",
                  usage={"web-design-mastery": dict(n=64, sessions=23, first="2026-09-01", last="2026-10-29", via={"tool": 64}),
                         "ghost-skill": dict(n=2, sessions=1, first="2026-09-01", last="2026-09-02", via={"tool": 2}),
                         "model": dict(n=9, sessions=3, first=None, last=None, via={"slash": 9})})
        p = skills_page.payload(ud)
        rows = {r["k"]: r for r in p["rows"]}
        if "web-design-mastery" in rows:
            self.assertEqual(rows["web-design-mastery"]["n"], 64)
        gone = {g["k"] for g in p["gone"]}
        self.assertIn("ghost-skill", gone)
        self.assertNotIn("model", gone)
        self.assertGreaterEqual(p["t0"], p["t1"])

    def test_render_escapes_and_fills(self):
        p = skills_page.payload(dict(files=0, scanned_at=None, usage={}))
        page = skills_page.render(p, "2026-10-30 12:00")
        self.assertIn("حصر المهارات", page)
        self.assertNotIn("__DATA__", page)
        self.assertNotIn("__LIB__", page)

    def test_usage_load_missing(self):
        self.assertEqual(skill_usage.load("/no/such/file.json")["usage"], {})

    def test_usage_scan(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            line1 = json.dumps({"type": "assistant", "timestamp": "2026-10-01T10:00:00Z",
                                "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "alpha"}}]}}, separators=(",", ":"))
            line2 = json.dumps({"type": "user", "timestamp": "2026-10-02T10:00:00Z",
                                "message": {"content": "<command-name>/beta</command-name>"}}, separators=(",", ":"))
            with open(os.path.join(d, "s1.jsonl"), "w", encoding="utf-8") as f:
                f.write(line1 + "\n" + line2 + "\n")
            res = skill_usage.scan(d)
        self.assertEqual(res["files"], 1)
        self.assertEqual(res["usage"]["alpha"]["n"], 1)
        self.assertEqual(res["usage"]["beta"]["via"], {"slash": 1})


if __name__ == "__main__":
    unittest.main()
