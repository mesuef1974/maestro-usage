import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import alerts  # noqa: E402


def q(full_at, resets="2026-11-11T17:00:00Z", at_reset=130):
    return {"week": {"cost": {}, "fc": {"full_at": full_at, "resets": resets, "at_reset": at_reset}}, "fable": {"cost": {}, "fc": {}}}


class TestAlerts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "alerts_state.json")
        self.sent = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def send(self, title, body):
        self.sent.append((title, body))
        return True

    def test_once_per_reset_then_again_after_clear_or_new_reset(self):
        self.assertEqual(alerts.run(q("2026-11-09T10:00:00Z"), self.path, self.send), 1)
        self.assertIn("تبلغ 100%", self.sent[0][1])
        self.assertEqual(alerts.run(q("2026-11-09T11:00:00Z"), self.path, self.send), 0)  # نفس التصفير: لا تكرار
        self.assertEqual(alerts.run(q(None), self.path, self.send), 0)  # زال التوقّع
        self.assertEqual(alerts.run(q("2026-11-09T12:00:00Z"), self.path, self.send), 1)  # عاد: إشعار جديد
        self.assertEqual(alerts.run(q("2026-11-15T12:00:00Z", resets="2026-11-18T17:00:00Z"), self.path, self.send), 1)  # تصفير جديد
        self.assertEqual(len(self.sent), 3)

    def test_no_forecast_sends_nothing(self):
        self.assertEqual(alerts.run({"week": {"cost": {}, "fc": None}}, self.path, self.send), 0)
        self.assertEqual(alerts.run({}, self.path, self.send), 0)
        self.assertEqual(self.sent, [])

    def test_notify_is_noop_off_windows(self):
        if sys.platform != "win32":
            self.assertFalse(alerts.notify("x", "y"))


if __name__ == "__main__":
    unittest.main()
