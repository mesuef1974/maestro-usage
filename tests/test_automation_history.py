"""تاريخ الأتمتة: دفتر صناعي صغير، والفهرس بلا نصّ حرّ، والنصوص تُقرأ عند العرض بعد الحجب."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import automation_history as ah  # noqa: E402
import pages  # noqa: E402
import usage_db  # noqa: E402
from test_whitelist import WHITELIST  # noqa: E402


def ev(ts, cid, kind, **data):
    return {"ts": "2026-11-0%sT10:00:00+03:00" % ts, "id": cid, "kind": kind, "data": data}


PUBLISHED = [
    ev(1, "W-1", "created", problem="عنوان منشور", impact="أثر", source="owner", priority="P1", req_type="خلل", runner_size="صغير",
       approval="مباشر", request_file="web-1"),
    ev(1, "W-1", "state", state="in_progress", by="runner"),
    ev(1, "W-1", "note", text="[مشغّل] sonnet تشغيل 1: كلفة=0.5$ أدوار=10", by="runner"),
    ev(1, "W-1", "note", text="[مشغّل] sonnet إصلاح CI 1: كلفة=0.25$ أدوار=4", by="runner"),
    ev(1, "W-1", "note", text="[مشغّل] مراجعة القبول: كلفة=0.05$ أدوار=1", by="runner"),
    ev(2, "W-1", "update", pr=1300),
    ev(2, "W-1", "state", state="pushed"),
    ev(2, "W-1", "state", state="merged"),
    ev(3, "W-1", "state", state="published"),
]
STOPPED = [
    ev(1, "W-2", "created", problem="عنوان متوقّف", impact="أثر", source="owner", request_file="web-2"),
    ev(1, "W-2", "state", state="in_progress"),
    ev(1, "W-2", "note", text="[مشغّل] sonnet تشغيل 1: كلفة=1.0$ أدوار=20"),
    ev(2, "W-2", "update", pr=1301),
    ev(2, "W-2", "note", text="[مشغّل] أُغلقت بتقرير: فحوصُ CI حمراء على الطلب 1301: pytest (كلفة=1.0$ من 3.0$)"),
    ev(2, "W-2", "state", state="closed"),
]
OLD = [
    ev(1, "W-3", "created", problem="بطاقة قديمة", source="alert"),
    ev(1, "W-3", "state", state="routed"),
    ev(1, "W-3", "note", text="فُتح الطلب #1200 آلياً من الفرع"),
]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "events.jsonl"
        self.write(PUBLISHED + STOPPED + OLD)
        self.con = usage_db.connect(os.path.join(self.tmp.name, "u.sqlite3"))
        self.addCleanup(self.con.close)
        ah._PARSED.clear()

    def write(self, events, tail=""):
        self.path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events) + tail, encoding="utf-8")

    def over(self, era="all", now="2026-11-09T07:00:00Z"):
        ah.sync(self.con, self.path)
        return ah.overview(self.con, era, self.path, now)


class TestSync(Base):
    def test_second_sync_touches_nothing(self):
        self.assertTrue(ah.sync(self.con, self.path)["synced"])
        self.assertEqual(ah.sync(self.con, self.path), {"synced": False, "reason": "unchanged"})

    def test_rebuild_gives_the_same_rows(self):
        ah.sync(self.con, self.path)
        before = self.con.execute("SELECT * FROM auto_cards ORDER BY card_id").fetchall()
        self.con.execute("DELETE FROM auto_sync")
        ah.sync(self.con, self.path)
        self.assertEqual(before, self.con.execute("SELECT * FROM auto_cards ORDER BY card_id").fetchall())

    def test_ledger_is_never_written(self):
        raw = self.path.read_bytes()
        self.over()
        self.assertEqual(raw, self.path.read_bytes())

    def test_truncated_last_line_is_skipped(self):
        self.write(PUBLISHED, tail='{"ts": "2026')
        self.assertEqual(ah.sync(self.con, self.path)["events"], len(PUBLISHED))

    def test_missing_ledger_is_reported(self):
        self.assertEqual(ah.sync(self.con, Path(self.tmp.name) / "none.jsonl")["reason"], "no-ledger")

    def test_no_free_text_reaches_the_tables(self):
        ah.sync(self.con, self.path)
        for table in ("auto_cards", "auto_events", "auto_sync"):
            for _cid, name, ctype, *_ in self.con.execute("PRAGMA table_info(%s)" % table).fetchall():
                if (ctype or "").upper() != "TEXT":
                    continue
                self.assertIn((table, name), WHITELIST)
                rx = re.compile(WHITELIST[(table, name)])
                for (v,) in self.con.execute("SELECT DISTINCT %s FROM %s WHERE %s IS NOT NULL" % (name, table, name)):
                    self.assertTrue(rx.fullmatch(str(v)), (table, name, v))


class TestSummary(Base):
    def row(self, cid):
        ah.sync(self.con, self.path)
        return ah.rows_of(self.con, "SELECT * FROM auto_cards WHERE card_id=?", (cid,))[0]

    def test_published_card(self):
        c = self.row("W-1")
        self.assertEqual((c["era"], c["state"], c["stage_rank"], c["pr"], c["runs"], c["ci_fixes"], c["turns"]),
                         ("auto", "published", 4, 1300, 1, 1, 15))
        self.assertAlmostEqual(c["cost_usd"], 0.8)
        self.assertEqual(c["duration_s"], 2 * 86400)
        self.assertIsNone(c["stop_key"])

    def test_closing_summary_is_not_counted_twice(self):
        self.assertAlmostEqual(self.row("W-2")["cost_usd"], 1.0)

    def test_stop_is_classified_with_its_last_stage(self):
        c = self.row("W-2")
        self.assertEqual((c["stop_key"], c["stage_rank"]), ("ci", 2))

    def test_card_without_runner_is_manual_and_pr_comes_from_note(self):
        c = self.row("W-3")
        self.assertEqual((c["era"], c["pr"]), ("manual", 1200))

    def test_timestamps_are_utc(self):
        self.assertEqual(self.row("W-1")["created_ts"], "2026-11-01T07:00:00Z")

    def test_stop_rules(self):
        cases = {"رفض المالك المعاينة على الطلب 1": "preview", "تعارض دمج مع main": "conflict", "تعذّر الإيداع: x": "commit",
                 "فشل النموذج بعد السلّم": "model", "لم يُحدث النموذجُ أيَّ تغيير في إصلاح CI على الطلب": "ci",
                 "أُغلقت بقرار المالك D-1م": "owner", "مكرَّرة: x": "duplicate", "شيء آخر": "other"}
        for text, key in cases.items():
            self.assertEqual(ah.stop_key("closed", text), key, text)
        self.assertEqual(ah.stop_key("deferred", ""), "deferred")
        self.assertIsNone(ah.stop_key("published", "تعارض دمج"))


class TestOverview(Base):
    def test_funnel_counts_every_stage(self):
        self.assertEqual([f["n"] for f in self.over()["funnel"]], [3, 2, 2, 1, 1])

    def test_era_scopes_everything(self):
        o = self.over("auto")
        self.assertEqual(o["totals"]["cards"], 2)
        self.assertEqual({c["card_id"] for c in o["cards"]}, {"W-1", "W-2"})
        self.assertEqual(self.over("manual")["totals"]["cost"], 0)

    def test_unknown_era_falls_back_to_all(self):
        self.assertEqual(self.over("x")["era"], "all")

    def test_stops_and_ops(self):
        o = self.over()
        self.assertEqual([(s["key"], s["n"], s["stages"]) for s in o["stops"]], [("ci", 1, [0, 0, 1, 0, 0])])
        self.assertEqual(sum(x["runs"] for x in o["ops"]), 4)
        self.assertAlmostEqual(sum(d["cost"] for d in o["daily"]), 1.8)

    def test_legs_skip_cards_before_the_runner(self):
        o = self.over("manual")
        self.assertTrue(all(leg["median_s"] is None for leg in o["legs"]))

    def test_idle_open_card_is_stalled(self):
        o = self.over()
        self.assertEqual([s["card_id"] for s in o["stalled"]], ["W-3"])
        self.assertEqual(self.over(now="2026-11-01T08:00:00Z")["stalled"], [])

    def test_personal_data_is_masked_on_display(self):
        self.write([ev(1, "W-9", "created", problem="هاتف 55512345 ورقم 28763400123"), ev(1, "W-9", "state", state="routed")])
        ah._PARSED.clear()
        title = self.over()["cards"][0]["title"]
        self.assertNotIn("28763400123", title)


class TestCard(Base):
    def test_timeline_carries_text_and_path(self):
        ah.sync(self.con, self.path)
        c = ah.card(self.con, "W-2", self.path)
        self.assertEqual((c["stop"], c["stage_label"]), ("CI", "طلب دمج"))
        self.assertIn("فحوصُ CI حمراء", c["reason"])
        self.assertTrue(c["pr_url"].endswith("/1301"))
        self.assertEqual([e["seq"] for e in c["timeline"]], [0, 1, 2, 3, 4, 5])

    def test_open_card_shows_what_it_waits_for(self):
        ah.sync(self.con, self.path)
        self.assertIn("فُتح الطلب", ah.card(self.con, "W-3", self.path)["waiting"])

    def test_unknown_card(self):
        ah.sync(self.con, self.path)
        self.assertIsNone(ah.card(self.con, "W-0", self.path))


class TestPage(unittest.TestCase):
    def test_page_is_registered_after_the_request_page(self):
        names = [p["file"] for p in pages.PAGES]
        self.assertEqual(names.index("automation"), names.index("request") + 1)

    def test_report_payload_carries_no_ledger_text(self):
        self.assertEqual(ah.payload(), {"automation": {"api": "automation.json", "card_api": "automation/card.json"}})

    def test_css_uses_tokens_and_logical_properties(self):
        css = (Path(__file__).parent.parent / "src" / "css" / "57-automation.css").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b", css))
        self.assertIsNone(re.search(r"(margin|padding|border)-(left|right)|text-align:(left|right)", css))

    def test_new_request_button_keeps_its_text_colour(self):
        css = (Path(__file__).parent.parent / "src" / "css" / "20-shell.css").read_text(encoding="utf-8")
        self.assertIn(".nav a.newreq:not([aria-current]){color:var(--on-brand)}", css)  # .nav a تغلب .newreq في اللون


if __name__ == "__main__":
    unittest.main()
