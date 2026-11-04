"""اختبار مسح حجم مجلد كلود وأدوات الحجر على شجرة مؤقتة: أرقام بحسب المجلد والمشروع والعمر، ثم معاينة ونقل واسترجاع وإفراغ،
وحدود الأمان (لا ملف حديث، لا سجل غير محمَّل، لا مجلد خارج الجذر)."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import ui  # noqa: E402
import storage_page  # noqa: E402
import storage_scan  # noqa: E402
import usage_db  # noqa: E402

DAY = 86400


def put(root, rel, size, age_days):
    p = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(b"x" * size)
    t = time.time() - age_days * DAY
    os.utime(p, (t, t))
    return p


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "claude")
        self.q = os.path.join(self.tmp, "quarantine")
        self.cwd_live = os.path.join(self.tmp, "live_project")
        os.makedirs(self.cwd_live)
        self.con = usage_db.connect(os.path.join(self.tmp, "u.sqlite3"))
        # مشروع حيّ P1: سجل قديم محمَّل كاملًا، سجل وكيل فرعي قديم غير محمَّل، سجل جديد
        put(self.root, "projects/P1/a.jsonl", 1000, 120)
        put(self.root, "projects/P1/subagents/b.jsonl", 500, 120)
        put(self.root, "projects/P1/c.jsonl", 300, 2)
        # مشروع يتيم P2 (مجلد عمله لا وجود له)
        put(self.root, "projects/P2/d.jsonl", 2000, 40)
        put(self.root, "projects/P2/e.jsonl", 100, 0.1)  # لُمس اليوم: لا يُنقل
        put(self.root, "file-history/f1", 700, 45)
        put(self.root, "file-history/f2", 50, 1)
        put(self.root, "shell-snapshots/s1", 20, 10)
        put(self.root, ".git/objects/pack", 5000, 200)
        put(self.root, "settings.json", 10, 5)
        self.con.executemany("INSERT INTO sessions(session_key, cwd, first_seen, last_seen) VALUES (?,?,?,?)",
                             [("s1", self.cwd_live, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
                              ("s2", os.path.join(self.tmp, "gone_worktree"), "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")])
        self.con.executemany("INSERT INTO ingest_state(source_path, offset_bytes, size_bytes, mtime, updated_at, session_key) VALUES (?,?,?,?,?,?)",
                             [("P1\\a.jsonl", 1000, 1000, 0, "2026-01-01T00:00:00Z", "s1"),
                              ("P1/subagents/b.jsonl", 100, 500, 0, "2026-01-01T00:00:00Z", "s1"),
                              ("P1/c.jsonl", 300, 300, 0, "2026-01-01T00:00:00Z", "s1"),
                              ("P2/d.jsonl", 2000, 2000, 0, "2026-01-01T00:00:00Z", "s2")])
        self.con.commit()

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_scan_aggregates_by_top_project_ext_and_age(self):
        s = storage_scan.scan(self.root)
        self.assertEqual((s["total"]["bytes"], s["total"]["files"]), (9680, 10))
        self.assertEqual(s["top"]["projects"]["bytes"], 3900)
        self.assertEqual((s["proj"]["P1"]["files"], s["proj"]["P1"]["jsonl"], s["proj"]["P1"]["sub"]), (3, 3, 500))
        self.assertEqual(s["ext"][".jsonl"]["files"], 5)
        self.assertEqual(s["top"]["projects"]["b7"], 400)  # c وe
        self.assertEqual(s["top"]["projects"]["b90p"], 1500)  # a وb
        self.assertEqual(s["top"][".git"]["b90p"], 5000)

    def test_persist_payload_and_hourly_due(self):
        self.assertTrue(storage_scan.due(self.con))
        r = storage_scan.run(self.con, self.root)
        self.assertEqual(r["scanned"], 1)
        self.assertFalse(storage_scan.due(self.con))  # قبل ساعة لا يُعاد
        self.assertEqual(storage_scan.run(self.con, self.root), {"scanned": 0})
        p = storage_page.payload(self.con)
        self.assertEqual(p["scan"]["bytes"], 9680)
        by = {r["name"]: r for r in p["proj"]}
        self.assertEqual((by["P1"]["exists"], by["P2"]["exists"]), (True, False))
        self.assertAlmostEqual(by["P1"]["ingested"], 1400 / 1800)
        kinds = {k["k"]: k for k in p["kinds"]}
        self.assertEqual(kinds["foreign"]["bytes"], 5000)  # .git ليس من Claude Code
        self.assertEqual(kinds["transcripts"]["bytes"], 3900)
        self.assertEqual(len(p["history"]), 1)
        html = ui.render("storage", p, {"__STAMP__": "الآن"})
        for s in ("من أين تأتي هذه الأحجام", "تحرير المساحة بأمان", 'id="tools"', "function fb("):
            self.assertIn(s, html)

    def test_plan_old_transcripts_only_fully_ingested_and_old(self):
        pl = storage_scan.plan("old_transcripts", 30, self.root, self.con)
        self.assertEqual((pl["files"], pl["bytes"]), (2, 3000))  # a (محمَّل، 120 يومًا) وd (محمَّل، 40 يومًا)؛ لا b (غير محمَّل) ولا c/e (حديثة)
        self.assertEqual([b["name"] for b in pl["by"]], ["P2", "P1"])
        self.assertEqual(storage_scan.plan("old_transcripts", 90, self.root, self.con)["files"], 1)

    def test_plan_orphans_file_history_and_snapshots(self):
        self.assertEqual(storage_scan.plan("orphan_projects", 0, self.root, self.con)["bytes"], 2000)  # P2 بلا e الحديث
        self.assertEqual(storage_scan.plan("file_history", 30, self.root, self.con)["files"], 1)
        self.assertEqual(storage_scan.plan("shell_snapshots", 7, self.root, self.con)["files"], 1)
        with self.assertRaises(ValueError):
            storage_scan.plan("settings", 0, self.root, self.con)

    def test_apply_restore_purge_roundtrip(self):
        r = storage_scan.apply("old_transcripts", 30, self.con, self.root, self.q)
        self.assertEqual((r["files"], r["bytes"]), (2, 3000))
        self.assertFalse(os.path.exists(os.path.join(self.root, "projects", "P1", "a.jsonl")))
        qdir = self.con.execute("SELECT qdir FROM storage_actions WHERE id=?", (r["id"],)).fetchone()[0]
        man = json.load(open(os.path.join(qdir, "manifest.json"), encoding="utf-8"))
        self.assertEqual(sorted(f["rel"] for f in man["files"]), ["projects/P1/a.jsonl", "projects/P2/d.jsonl"])
        rows = storage_scan.quarantine_rows(self.con)
        self.assertEqual((rows[0]["status"], rows[0]["disk"]), ("quarantined", 3000))
        b = storage_scan.restore(r["id"], self.con, self.root, self.q)
        self.assertEqual(b["files"], 2)
        self.assertTrue(os.path.exists(os.path.join(self.root, "projects", "P1", "a.jsonl")))
        self.assertFalse(os.path.isdir(qdir))
        self.assertEqual(self.con.execute("SELECT status FROM storage_actions WHERE id=?", (r["id"],)).fetchone()[0], "restored")
        with self.assertRaises(ValueError):
            storage_scan.restore(r["id"], self.con, self.root, self.q)
        r2 = storage_scan.apply("file_history", 30, self.con, self.root, self.q)
        self.assertEqual(storage_scan.purge(r2["id"], self.con, self.q)["bytes"], 700)
        self.assertFalse(os.path.exists(os.path.join(self.root, "file-history", "f1")))
        self.assertEqual(self.con.execute("SELECT status FROM storage_actions WHERE id=?", (r2["id"],)).fetchone()[0], "purged")

    def test_handle_requires_confirm_for_changes(self):
        with self.assertRaises(ValueError):
            storage_scan.handle("apply", {"group": "file_history", "days": 30}, self.con, self.root, self.q)
        self.assertEqual(storage_scan.handle("plan", {"group": "file_history", "days": 30}, self.con, self.root, self.q)["files"], 1)
        self.assertTrue(os.path.exists(os.path.join(self.root, "file-history", "f1")))
        out = storage_scan.handle("apply", {"group": "file_history", "days": 30, "confirm": True}, self.con, self.root, self.q)
        self.assertEqual(out["files"], 1)

    def test_inside_guard(self):
        self.assertTrue(storage_scan._inside(os.path.join(self.root, "projects", "x"), self.root))
        self.assertFalse(storage_scan._inside(os.path.join(self.tmp, "live_project"), self.root))
        self.assertFalse(storage_scan._inside(self.root + "_other", self.root))


if __name__ == "__main__":
    unittest.main()
