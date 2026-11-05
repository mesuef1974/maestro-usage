import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestMetricsDoc(unittest.TestCase):
    def test_doc_matches_registry(self):
        """docs/metrics.md مولَّد من سجلّ المقاييس؛ تغيّر السجلّ دون إعادة التوليد يُفشل هذا الاختبار."""
        rc = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "gen_metrics_doc.py"), "--check"], timeout=60).returncode
        self.assertEqual(rc, 0, "شغّل: python scripts/gen_metrics_doc.py")


if __name__ == "__main__":
    unittest.main()
