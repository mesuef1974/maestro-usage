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

    def test_password_read_from_env_file(self):
        env = Path(self.tmp.name) / "a.env"
        env.write_text("PREVIEW_ACCOUNTS_PASSWORD=x1" + chr(10), encoding="utf-8")
        self.assertEqual(pd.password(env=env)["password"], "x1")


if __name__ == "__main__":
    unittest.main()
