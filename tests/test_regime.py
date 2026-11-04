"""اختبار تصنيف نظام نافذة السياق للردّ: بدء معروف، واستدلال بما يمكن الجزم به، وغير محدد حيث لا جزم."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import regime  # noqa: E402
import usage_db  # noqa: E402

D, W250, W1M, U = regime.DEFAULT, regime.W250, regime.W1M, regime.UNKNOWN
BEFORE = "2026-10-20T00:00:00Z"
DAY29 = "2026-10-29T12:00:00Z"
EARLY30 = "2026-10-30T01:00:00Z"
AFTER = "2026-10-30T05:00:00Z"


class TestRegime(unittest.TestCase):
    def test_changes_from_seeds(self):
        ch = regime.changes()
        self.assertEqual(ch[0], ("2026-10-29T00:00:00Z", W250))
        self.assertEqual(ch[-1], ("2026-10-30T03:04:17Z", W1M))

    def test_known_start_decides(self):
        self.assertEqual(regime.classify(AFTER, BEFORE, ["2026-10-30T04:00:00Z"]), W1M)
        self.assertEqual(regime.classify(AFTER, BEFORE, ["2026-10-30T01:00:00Z"]), W250)
        self.assertEqual(regime.classify(AFTER, BEFORE, ["2026-10-19T01:00:00Z"]), D)

    def test_latest_start_not_after_reply_wins(self):
        starts = ["2026-10-30T01:00:00Z", "2026-10-30T04:00:00Z"]
        self.assertEqual(regime.classify(EARLY30, BEFORE, starts), W250)
        self.assertEqual(regime.classify(AFTER, BEFORE, starts), W1M)

    def test_unknown_start_inference(self):
        self.assertEqual(regime.classify(BEFORE, BEFORE, []), D)                 # قبل أول تغيير: جزم
        self.assertEqual(regime.classify(DAY29, DAY29, []), W250)                # جلسة وُلدت بعد أول تغيير وقبل الأخير
        self.assertEqual(regime.classify(EARLY30, BEFORE, []), U)                # جلسة أقدم: قد تكون افتراضية
        self.assertEqual(regime.classify(AFTER, DAY29, []), U)                   # بعد آخر تغيير: قد تكون العملية أقدم
