"""صفحة حصر المهارات: الحصر من الملفات، دمج الاستعمال، وسلامة التوصيات والتوليد، وتفريد الماسح بالمعرّفات."""
import json
import os
import re
import sys
import tempfile
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

    def test_notes_carry_no_manual_counts(self):
        """عمود الاستدعاءات هو مصدر العدّ؛ الملاحظات اليدوية لا تحمل أعدادًا تنحرف عنه."""
        count = re.compile(r"\d+\s*(استدعاء|مر[ةا]ت?\b|جلسة)|استدعاء(ان|ين|\s+واحد)|استدعاءات|مرتين|ثلاث مرات")
        notes = [(k, v[3]) for k, v in skills_page.CURATION.items()] + [(v[0], v[6]) for v in skills_page.VIRTUAL]
        for key, note in notes:
            self.assertIsNone(count.search(note), (key, note))

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

    def test_estimated_lengths_flagged(self):
        """المهارات المضمَّنة بطول مخمَّن تحمل est=True والأرقام نفسها؛ صفوف القرص est=False ومعها أحرف الملف."""
        p = skills_page.payload(dict(files=0, scanned_at=None, usage={}))
        rows = {r["k"]: r for r in p["rows"]}
        guessed = {v[0] for v in skills_page.VIRTUAL if v[2]}
        self.assertTrue(guessed)
        for key in guessed:
            self.assertTrue(rows[key]["est"], key)
            self.assertIsNone(rows[key]["file_chars"], key)
        chars = dict((v[0], v[2]) for v in skills_page.VIRTUAL)
        self.assertEqual(rows["code-review (مضمَّنة)"]["t0"], round(chars["code-review (مضمَّنة)"] / skills_page.CHARS_PER_TOKEN))
        for r in p["rows"]:
            if r["file_chars"] is not None:
                self.assertFalse(r["est"], r["k"])
            self.assertNotIn("size", r)
        page = skills_page.render(p, "2026-11-01 05:00")
        self.assertIn("≈ تقدير", page)

    def test_render_escapes_and_fills(self):
        p = skills_page.payload(dict(files=0, scanned_at=None, usage={}))
        page = skills_page.render(p, "2026-10-30 12:00")
        self.assertIn("حصر المهارات", page)
        self.assertNotIn("__DATA__", page)
        self.assertNotIn("__LIB__", page)

    def test_usage_load_missing(self):
        self.assertEqual(skill_usage.load("/no/such/file.json")["usage"], {})

    def test_usage_scan(self):
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

    def test_usage_scan_dedups_by_ids_and_owner(self):
        """الاستئناف ينسخ التاريخ: tool_use بمعرّفه مرة واحدة، والأمر المائل بمعرّف رسالته، والوكيل الفرعي يُنسب إلى جلسة المالك."""
        sep = (",", ":")
        tool = json.dumps({"type": "assistant", "uuid": "u1", "timestamp": "2026-10-01T10:00:00Z", "message": {"id": "msg_1", "content": [
            {"type": "tool_use", "id": "toolu_A", "name": "Skill", "input": {"skill": "alpha"}}]}}, separators=sep)
        slash = json.dumps({"type": "user", "uuid": "u2", "timestamp": "2026-10-01T10:01:00Z",
                            "message": {"content": "<command-name>/beta</command-name>"}}, separators=sep)
        sub = json.dumps({"type": "assistant", "uuid": "u3", "timestamp": "2026-10-01T10:02:00Z", "message": {"id": "msg_3", "content": [
            {"type": "tool_use", "id": "toolu_B", "name": "Skill", "input": {"skill": "alpha"}}]}}, separators=sep)
        noid = json.dumps({"type": "assistant", "timestamp": "2026-10-03T10:00:00Z", "message": {"content": [
            {"type": "tool_use", "name": "Skill", "input": {"skill": "gamma"}}]}}, separators=sep)
        with tempfile.TemporaryDirectory() as d:
            proj = os.path.join(d, "proj")
            os.makedirs(os.path.join(proj, "s1", "subagents"))
            with open(os.path.join(proj, "s1.jsonl"), "w", encoding="utf-8") as f:
                f.write(tool + "\n" + slash + "\n" + noid + "\n" + noid + "\n")
            with open(os.path.join(proj, "s2.jsonl"), "w", encoding="utf-8") as f:  # جلسة مستأنفة نسخت التاريخ
                f.write(tool + "\n" + slash + "\n")
            with open(os.path.join(proj, "s1", "subagents", "agent-x.jsonl"), "w", encoding="utf-8") as f:
                f.write(sub + "\n")
            res = skill_usage.scan(d)
            again = skill_usage.scan(d)
        u = res["usage"]
        self.assertEqual(res["files"], 3)
        self.assertEqual((u["alpha"]["n"], u["alpha"]["sessions"]), (2, 1))  # A في s1 وB في وكيل s1؛ نسخة s2 لا تُعدّ
        self.assertEqual((u["beta"]["n"], u["beta"]["sessions"]), (1, 1))
        self.assertEqual((u["gamma"]["n"], u["gamma"]["sessions"]), (2, 1))  # بلا معرّف: كل سطر يُعدّ بموضعه
        self.assertEqual(u["alpha"]["via"], {"tool": 2})
        self.assertEqual(again["usage"], u)  # إعادة المسح لا تغيّر الأرقام


if __name__ == "__main__":
    unittest.main()
