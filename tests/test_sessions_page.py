"""اختبار صفحة الأدوار والجلسات: الإيقاظ وهبوط السياق وتصنيف الأدوار على قاعدة صناعية بأرقام معروفة."""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import reports  # noqa: E402
import role_groups  # noqa: E402
import sessions_page  # noqa: E402
import usage_db  # noqa: E402


class TestSessionsPage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = usage_db.connect(os.path.join(self.tmp, "u.sqlite3"))
        c = self.con
        c.execute("INSERT INTO sessions(session_key, number, cwd) VALUES "
                  "('aaaaaaaa1','0101','D:/shschool_mvp/.claude/worktrees/wt-x'),('bbbbbbbb2','0101','D:/y'),"
                  "('cccccccc3',NULL,'D:/z'),('dddddddd4','8094','D:/w')")

        def t(i, s, ts, cc, cr, u=1, side=0, org="human", model="claude-sonnet-5-5"):
            c.execute("INSERT INTO usage_turns(message_id,session_key,ts,model,input_tokens,cache_creation_tokens,cache_read_tokens,"
                      "output_tokens,thinking_tokens,is_sidechain,source_path,turn_origin) VALUES (?,?,?,?,1,?,?,?,0,?,'p.jsonl',?)",
                      (i, s, ts, model, cc, cr, u, side, None if side else org))
        # aaaaaaaa1: الأول ليس إيقاظًا، الثاني بعد 10 دقائق، الثالث بعد ساعتين (إيقاظ)، الرابع يهبط من 400 ألف إلى 50 ألفًا
        t("1", "aaaaaaaa1", "2026-10-20T01:00:00Z", 100, 399_000)
        t("2", "aaaaaaaa1", "2026-10-20T01:10:00Z", 10, 400_000)
        t("3", "aaaaaaaa1", "2026-10-20T03:10:00Z", 5000, 400_000, org="scheduled")
        t("4", "aaaaaaaa1", "2026-10-20T03:11:00Z", 20, 50_000)
        t("5", "aaaaaaaa1", "2026-10-20T03:12:00Z", 0, 30_000, side=1)  # وكيل فرعي: لا يدخل الإيقاظ ولا الهبوط ولا العتبة
        t("6", "bbbbbbbb2", "2026-10-21T01:00:00Z", 0, 10_000, model="model-قديم")
        t("7", "cccccccc3", "2026-10-21T02:00:00Z", 0, 20_000)
        t("8", "dddddddd4", "2026-10-21T03:00:00Z", 0, 5_000)
        c.commit()
        self.data = sessions_page.payload(c)

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def agg(self, sess_idx=None):
        rows = [r for r in self.data["c"] if sess_idx is None or r["s"] == sess_idx]
        return {k: sum(r[k] for r in rows) for k in ("t", "cr", "cc", "u", "v", "dr", "wk", "wc")}

    def idx(self, key8):
        return next(i for i, s in enumerate(self.data["sessions"]) if s["k"] == key8)

    def test_totals_match_db(self):
        want = self.con.execute("SELECT COUNT(*), SUM(cache_read_tokens), SUM(cache_creation_tokens), SUM(output_tokens) FROM usage_turns").fetchone()
        a = self.agg()
        self.assertEqual((a["t"], a["cr"], a["cc"], a["u"]), tuple(want))

    def test_wake_and_drop_counts(self):
        a = self.agg(self.idx("aaaaaaaa"))
        self.assertEqual((a["wk"], a["wc"]), (1, 5000))  # ردّ 3 وحده؛ الأول بلا سابق، والفرعي مستثنى
        self.assertEqual(a["dr"], 1)                      # 400 ألف ← 50 ألفًا عند الردّ 4
        self.assertEqual(a["v"], 3)                       # الردود 1 و2 و3 سياقها فوق 300 ألف؛ الفرعي لا يُحسب
        self.assertEqual(self.agg()["wk"], 1)

    def test_sidechain_is_own_origin_and_has_no_pressure(self):
        sub = [r for r in self.data["c"] if r["g"] == "sub"]
        self.assertEqual(len(sub), 1)
        self.assertEqual((sub[0]["v"], sub[0]["mx"], sub[0]["dr"], sub[0]["wk"], sub[0]["wc"]), (0, 0, 0, 0, 0))

    def test_roles_and_project_flag(self):
        roles = {r["n"]: r["p"] for r in self.data["roles"]}
        self.assertEqual(roles, {"0101": True, role_groups.OTHER: False, "8094": False})
        s = self.data["sessions"]
        self.assertEqual(self.data["roles"][s[self.idx("aaaaaaaa")]["r"]]["n"], "0101")
        self.assertEqual(s[self.idx("aaaaaaaa")]["r"], s[self.idx("bbbbbbbb")]["r"])  # جلستان تحت دور واحد

    def test_old_model_folds_into_other(self):
        other = len(self.data["models"]) - 1
        r = next(r for r in self.data["c"] if r["s"] == self.idx("bbbbbbbb"))
        self.assertEqual(r["m"], other)

    def test_folder_label(self):
        self.assertEqual(sessions_page.folder_label("D:/shschool_mvp/.claude/worktrees/wt-x"), "shschool_mvp › wt-x")
        self.assertEqual(sessions_page.folder_label("C:\\Users\\m\\maestro_usage"), "maestro_usage")
        self.assertEqual(sessions_page.folder_label(None), "")
        self.assertEqual([s["f"] for s in self.data["sessions"] if s["k"] == "aaaaaaaa"], ["shschool_mvp › wt-x"])

    def test_payload_whitelist_and_render(self):
        """الحقول النصية: معرّف الجلسة (8 أحرف)، الرقم، المجلد، اليوم، الأصل المعروف. لا شيء غيرها."""
        for s in self.data["sessions"]:
            self.assertEqual(set(s), {"k", "n", "f", "r", "st", "ns"})
            self.assertTrue(s["st"] is None or re.fullmatch(r"\d{4}-\d\d-\d\dT[\d:.]+Z", s["st"]))
        for r in self.data["c"]:
            self.assertIn(r["x"], range(len(self.data["regimes"])))
            self.assertRegex(r["d"], r"^\d{4}-\d\d-\d\d$")
            self.assertIn(r["g"], ("human", "peer", "scheduled", "sdk", "task_notification", "system", "unknown", "sub"))
        self.data["sessions"][0]["f"] = "</script><b>"
        page = sessions_page.render(self.data, "الآن")
        m = re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S)
        self.assertEqual(json.loads(m.group(1))["sessions"][0]["f"], "</script><b>")
        for token in ("__CSS__", "__LIB__", "__DATA__", "__STAMP__"):
            self.assertNotIn(token, page)

    def test_build_writes_sessions_page_without_external_resources(self):
        out = os.path.join(self.tmp, "out")
        reports.build(self.con, out)
        with open(os.path.join(out, "roles.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertEqual(html.replace("http://www.w3.org/2000/svg", "").count("http"), 0)
        self.assertEqual(html.count("fetch("), html.count('fetch("/refresh"'))
        links = re.findall(r"<link[^>]*>", html)  # الرابطان المحلّيان فقط: أيقونة data: والأسلوب المركزي من assets/
        self.assertEqual(len(links), 2, links)
        self.assertTrue(all('href="data:image/svg+xml' in ln or 'href="assets/platform.css?v=' in ln for ln in links), links)
        for bad in ("@import", "XMLHttpRequest", "<script src"):
            self.assertNotIn(bad, html)


if __name__ == "__main__":
    unittest.main()
