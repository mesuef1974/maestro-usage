"""الصفحة الواحدة المجمَّعة: معرّفات فريدة، وكل قسم له مرساة، ومعطيات كل جزء بوسم خاص، وصفحات ما قبل الدمج تُزال."""
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pages  # noqa: E402
import reports  # noqa: E402
import usage_db  # noqa: E402
import onepage  # noqa: E402
import ui  # noqa: E402


class TestOnePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.con = usage_db.connect(os.path.join(cls.tmp, "u.sqlite3"))
        cls.out = os.path.join(cls.tmp, "out")
        os.makedirs(cls.out)
        open(os.path.join(cls.out, "plan.html"), "w").write("قديمة")  # صفحة من زمن ما قبل الدمج
        cls.path = reports.build(cls.con, cls.out)
        cls.html = open(cls.path, encoding="utf-8").read()
        cls.body = re.sub(r"<script.*?</script>", "", cls.html, flags=re.S)  # الوسوم بلا النصوص البرمجية

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_only_index_html_remains(self):
        self.assertEqual([n for n in os.listdir(self.out) if n.endswith(".html")], ["index.html"])

    def test_ids_are_unique_across_parts(self):
        ids = re.findall(r'\sid="([^"]+)"', self.body)
        dup = sorted({i for i in ids if ids.count(i) > 1})
        self.assertEqual(dup, [])

    def test_every_section_has_one_anchor_and_nav_link(self):
        for sid, _title, _icon in pages.SECTIONS:
            self.assertEqual(self.body.count('<h2 class="gh" id="%s">' % sid), 1, sid)
            self.assertEqual(self.body.count('<li><a href="#%s">' % sid), 1, sid)

    def test_each_part_data_has_its_own_tag_and_reader(self):
        for p in pages.PAGES:
            if p["file"] in pages.SCRIPTLESS:
                continue
            self.assertEqual(self.html.count('<script type="application/json" id="data-%s">' % p["file"]), 1, p["file"])
            self.assertEqual(self.html.count('getElementById("data-%s")' % p["file"]), 1, p["file"])
        self.assertNotIn('getElementById("data")', self.html)

    def test_shared_widgets_appear_once(self):
        for needle in ('id="themeslot"', 'id="tip"', 'id="refresh"', "<h1>"):
            self.assertEqual(self.body.count(needle), 1, needle)
        for tok in ("__SHELL_", "__DATA__", "__LIB__", "__STAMP__", "__STATIC__", "<!--@"):
            self.assertNotIn(tok, self.html)

    def test_no_external_resources_and_local_fetches_only(self):
        self.assertEqual(self.html.replace("http://www.w3.org/2000/svg", "").count("http"), 0)
        self.assertNotIn('fetch("http', self.html)
        for bad in ("@import", "XMLHttpRequest", "<script src"):
            self.assertNotIn(bad, self.html)
        self.assertLess(self.html.index("mu_theme"), self.html.index("</head>"))  # السمة المحفوظة تُطبَّق قبل الرسم

    def test_fold_and_rail_scripts_present(self):
        self.assertIn("mu_fold", self.html)
        self.assertIn("IntersectionObserver", self.html)


if __name__ == "__main__":
    unittest.main()


class TestSharedLibOnce(unittest.TestCase):
    def test_shared_lib_embedded_once_and_state_per_part(self):
        """المكتبة المشتركة مرة واحدة في الصفحة؛ ودوال حالة الجزء (setPreset) داخل كل جزء له مرشِّحات."""
        import flow_page
        import skills_page
        parts = [("skills", ui.render("skills", skills_page.payload(dict(files=0, scanned_at=None, usage={})), {"__STAMP__": "x"}), False),
                 ("flow", ui.render("flow", flow_page.payload(), {"__STAMP__": "x"}), False)]
        page = onepage.build(parts, "x")
        self.assertEqual(page.count("function drawLines("), 1)
        self.assertEqual(page.count("function showTip("), 1)
        self.assertNotIn(ui.LIB_MARK, page.split("(function(){", 1)[0])  # المشترك قبل أول جزء بلا علامة الحالة
        shared, state = ui.lib_split()
        self.assertIn("function setPreset(", state)
        self.assertNotIn("function setPreset(", shared)


class TestHero(unittest.TestCase):
    def test_hero_strip_only_on_one_page_and_filled_by_parts(self):
        import flow_page
        page = onepage.build([("flow", ui.render("flow", flow_page.payload(), {"__STAMP__": "x"}), False)], "x")
        self.assertEqual(page.count('id="hero"'), 1)
        for i in ("hero-pct", "hero-full", "hero-run"):
            self.assertIn('id="%s"' % i, page)
        self.assertNotIn('id="hero"', ui.pagehead("t", "l", "x"))  # الأجزاء المنفردة بلا شريط
        self.assertIn("function heroQuota", (ui.SRC / "dashboard.html").read_text(encoding="utf-8"))
        self.assertIn('getElementById("hero-run")', (ui.SRC / "runner.html").read_text(encoding="utf-8"))
        self.assertIn('!card.hasAttribute("data-open")', (ui.SRC / "fold.js").read_text(encoding="utf-8"))  # الافتراضي مطويّ
