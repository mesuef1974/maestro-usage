"""مكتب المعاينة: ما يُعرض من الدفتر، وحراسة زرّي الاعتماد والرفض."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import automation_history as ah  # noqa: E402
import preview_desk as pd  # noqa: E402
import request_page  # noqa: E402

HEAD = "abcdef1234567890"


def ledger_file(folder, *events):
    path = Path(folder) / "events.jsonl"
    path.write_text("".join(json.dumps(e, ensure_ascii=False) + chr(10) for e in events), encoding="utf-8")
    return path


def card_events(cid="W-20261107-001", seen=HEAD, approved=None, approval="معاينة", state="in_progress"):
    base = dict(ts="2026-11-07T01:00:00+03:00", id=cid)
    update = dict(runner_resume=dict(head=HEAD, pr=7), preview_seen=seen,
                  preview_info=dict(url="http://localhost:8500/x/", account="99900001", role="المدير", checks=["فحص"]))
    if approved:
        update["preview_approved"] = True
    return [dict(base, kind="created", data=dict(problem="عنوان البطاقة", approval=approval)),
            dict(base, kind="state", data=dict(state=state)), dict(base, kind="update", data=update)]


class Desk(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        ah._PARSED.clear()

    def cards(self, served="abcdef1", **kw):
        return pd.waiting(ledger_file(self.tmp.name, *card_events(**kw)), served)

    def test_ready_only_when_8500_serves_the_head(self):
        self.assertTrue(self.cards()[0]["ready"])
        ah._PARSED.clear()
        self.assertFalse(self.cards(served="9999999")[0]["ready"])

    def test_a_card_on_a_slot_is_judged_by_that_slot_not_8500(self):
        events = card_events()
        events[2]["data"]["preview_info"]["url"] = "http://localhost:8601/x/"
        path = ledger_file(self.tmp.name, *events)
        seen = []
        real = pd.served_commit
        pd.served_commit = lambda url: seen.append(url) or "abcdef1"
        self.addCleanup(setattr, pd, "served_commit", real)
        self.assertTrue(pd.waiting(path, "9999999")[0]["ready"])
        self.assertEqual(seen, ["http://localhost:8601/health/"])

    def test_not_listed_after_approval_or_for_direct_cards_or_closed(self):
        self.assertEqual(self.cards(approved=True), [])
        ah._PARSED.clear()
        self.assertEqual(self.cards(approval="مباشر"), [])
        ah._PARSED.clear()
        self.assertEqual(self.cards(state="closed"), [])

    def test_approve_refuses_a_card_not_on_8500(self):
        cards = [dict(card_id="W-20261107-001", ready=False)]
        with self.assertRaises(request_page.ValidationError):
            pd.decide(dict(card="W-20261107-001", approve=True), cards=cards, run=self.fail)

    def test_reject_needs_a_reason(self):
        cards = [dict(card_id="W-20261107-001", ready=True)]
        with self.assertRaises(request_page.ValidationError):
            pd.decide(dict(card="W-20261107-001", approve=False, reason="  "), cards=cards, run=self.fail)

    def test_bad_or_unknown_card_never_reaches_the_runner(self):
        for cid in ("--approve", "W-20261107-999"):
            with self.assertRaises(request_page.ValidationError):
                pd.decide(dict(card=cid, approve=True), cards=[], run=self.fail)

    def test_only_literal_true_approves(self):
        seen = []

        def run(cmd, **kw):
            seen.append(cmd)
            return SimpleNamespace(returncode=0, stdout="تم", stderr="")

        cards = [dict(card_id="W-20261107-001", ready=True)]
        pd.decide(dict(card="W-20261107-001", approve=True), cards=cards, run=run)
        pd.decide(dict(card="W-20261107-001", approve="true", reason="سبب"), cards=cards, run=run)
        self.assertIn("--approve", seen[0])
        self.assertIn("--reject", seen[1])

    def closed_card(self, cid="W-20261107-005", request="web-20261107-010101", extra=()):
        base = dict(ts="2026-11-07T01:00:00+03:00", id=cid)
        return [dict(base, kind="created", data=dict(problem="عنوان", request_file=request)),
                dict(base, kind="note", data=dict(text="[مشغّل] sonnet تشغيل 1: كلفة=1.25$ أدوار=3")),
                dict(base, kind="note", data=dict(text="[مشغّل] أُغلقت بتقرير: فشل الفحص")),
                dict(base, kind="state", data=dict(state="closed")), *extra]

    def needs(self, *events):
        return pd.needs_decision(ledger_file(self.tmp.name, *events), pending=set())

    def merge_events(self, state="in_progress", cid="W-20261108-040"):
        base = dict(ts="2026-11-08T01:00:00+03:00", id=cid)
        return [dict(base, kind="created", data=dict(problem="تسجيل المخالفة")),
                dict(base, kind="update", data=dict(owner_action=dict(kind="merge", pr=1406, head="h", reason="مساراتٌ محظورةٌ: behavior/migrations/0026_x.py"))),
                dict(base, kind="state", data=dict(state=state))]

    def test_a_pr_waiting_for_the_owner_to_merge_shows_with_its_link(self):
        got = pd.merges(ledger_file(self.tmp.name, *self.merge_events()))
        self.assertEqual([c["card_id"] for c in got], ["W-20261108-040"])
        self.assertEqual(got[0]["pr_url"], pd.PR_URL + "1406")
        self.assertIn("migrations", got[0]["reason"])

    def test_it_leaves_when_the_card_is_published_or_closed(self):
        for state in ("published", "closed"):
            self.assertEqual(pd.merges(ledger_file(self.tmp.name, *self.merge_events(state))), [])

    def test_payload_carries_merges(self):
        self.assertIn("merges", pd.payload(ledger_file(self.tmp.name, *self.merge_events())))

    def test_a_failed_card_stays_until_decided(self):
        got = self.needs(*self.closed_card())
        self.assertEqual([c["card_id"] for c in got], ["W-20261107-005"])
        self.assertEqual(got[0]["cost"], 1.25)
        self.assertIn("فشل الفحص", got[0]["reason"])

    def test_retried_dismissed_and_old_cards_leave(self):
        retry = dict(ts="2026-11-07T02:00:00+03:00", id="W-20261107-009", kind="created", data=dict(problem="ع", retry_of="web-20261107-010101"))
        self.assertEqual(self.needs(*self.closed_card(), retry), [])
        ah._PARSED.clear()
        drop = dict(ts="2026-11-07T02:00:00+03:00", id="W-20261107-005", kind="update", data=dict(owner_dismissed=True))
        self.assertEqual(self.needs(*self.closed_card(extra=[drop])), [])
        ah._PARSED.clear()
        self.assertEqual(self.needs(*self.closed_card(cid="W-20261106-005")), [])

    def test_a_retry_not_yet_picked_up_hides_the_card(self):
        folder = Path(self.tmp.name)
        (folder / "web-20261107-020202.md").write_text("النوع: إصلاح" + chr(10) + "إعادة لـ: web-20261107-010101" + chr(10), encoding="utf-8")
        pending = pd.pending_retries(folder)
        self.assertEqual(pending, {"web-20261107-010101"})
        self.assertEqual(pd.needs_decision(ledger_file(self.tmp.name, *self.closed_card()), pending=pending), [])

    def test_retry_and_dismiss_refuse_cards_not_waiting(self):
        for fn in (pd.retry, pd.dismiss):
            with self.assertRaises(request_page.ValidationError):
                fn(dict(card="W-20261107-005"), needs=[])

    def test_a_live_twin_card_blocks_a_new_retry_but_a_finished_one_does_not(self):
        live = card_events("W-20261107-031", state="in_progress")
        old = card_events("W-20261107-030", state="closed")
        path = ledger_file(self.tmp.name, *old, *live)
        self.assertEqual(pd._live_twin("W-20261107-030", "عنوان البطاقة", path), "W-20261107-031")
        self.assertEqual(pd._live_twin("W-20261107-031", "عنوان البطاقة", path), "")
        done = ledger_file(self.tmp.name, *old, *card_events("W-20261107-031", state="published"))
        self.assertEqual(pd._live_twin("W-20261107-030", "عنوان البطاقة", done), "")

    def test_a_card_upgraded_to_preview_by_the_runner_reaches_the_desk(self):
        ev = card_events("W-20261109-001", approval="مباشر")
        ev.append(dict(ts="2026-11-09T15:22:51+03:00", id="W-20261109-001", kind="update", data=dict(approval="معاينة")))
        path = ledger_file(self.tmp.name, *ev)
        ah._PARSED.clear()
        self.assertEqual([c["card_id"] for c in pd.waiting(path, served="abcdef1")], ["W-20261109-001"])

    def test_password_read_from_env_file(self):
        env = Path(self.tmp.name) / "a.env"
        env.write_text("PREVIEW_ACCOUNTS_PASSWORD=x1" + chr(10), encoding="utf-8")
        self.assertEqual(pd.password(env=env)["password"], "x1")


if __name__ == "__main__":
    unittest.main()


def test_live_cards_show_stage_and_since(tmp_path):
    """بطاقةٌ فتحت طلبها ولم تبلغ المعاينة تظهر بمرحلتها ومنذ متى (013، 2026-11-09)."""
    path = tmp_path / "events.jsonl"
    rows = [
        {"id": "W-20261109-013", "kind": "created", "data": {"problem": "ع", "approval": "معاينة"}},
        {"id": "W-20261109-013", "kind": "state", "data": {"state": "in_progress"}},
        {"id": "W-20261109-013", "kind": "update", "data": {"runner_resume": {"pr": 7, "head": "abc"}}},
        {"id": "W-20261109-013", "kind": "update", "data": {"waiting": {"stage": "waiting_ci", "text": "ينتظر فحوص CI على الطلب", "since": 100}}},
    ]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    out = pd.live(path)
    assert out[0]["stage"] == "ينتظر فحوص CI على الطلب" and out[0]["since"] == 100 and out[0]["pr"] == 7
