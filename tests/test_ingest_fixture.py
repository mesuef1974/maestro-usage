"""عيّنة ثابتة بشكل نسخة Claude Code النصية الحقيقية (نوفمبر 2026): تكشف أي انزياح في الصيغة أو في المحلّل."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import usage_ingest  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "transcript_2026-11.jsonl")


class TestTranscriptFixture(unittest.TestCase):
    def setUp(self):
        with open(FIXTURE, encoding="utf-8") as f:
            self.lines = [ln for ln in f.read().splitlines() if ln]

    def test_shape_is_parsed_exactly(self):
        best, number, synthetic, bad, origin = usage_ingest.parse_lines(self.lines)
        self.assertEqual(bad, 0)
        self.assertEqual(synthetic, 0)
        self.assertEqual(set(best), {"msg_A", "msg_B", "msg_C"})  # السطران المبثوثان لردّ واحد = ردّ واحد
        a = best["msg_A"]
        self.assertEqual((a["inp"], a["cc"], a["cc1h"], a["cc5m"], a["cr"], a["out"]), (2, 1215, 1215, 0, 382471, 767))  # أعلى مخرجات تفوز
        self.assertEqual(a["think"], 383)
        self.assertEqual(a["req"], "req_A")
        self.assertEqual(a["side"], 0)
        c = best["msg_C"]
        self.assertEqual((c["side"], c["model"], c["cc5m"], c["cc1h"]), (1, "claude-haiku-5-5", 300, 0))
        self.assertEqual(origin, "human")  # آخر سطر مستخدم يحمل turnOrigin

    def test_non_message_lines_are_ignored(self):
        """سطور cost-state وmode وqueue-operation وattachment وsystem لا تُنتج ردودًا ولا أخطاء."""
        extra = [ln for ln in self.lines if '"type":"assistant"' not in ln and '"type":"user"' not in ln]
        self.assertGreaterEqual(len(extra), 7)
        best, _n, _s, bad, _o = usage_ingest.parse_lines(extra)
        self.assertEqual((best, bad), ({}, 0))


if __name__ == "__main__":
    unittest.main()
