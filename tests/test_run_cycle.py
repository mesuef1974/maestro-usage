"""اختبار قرار بناء التقارير في دورة الاستيعاب: كل دقيقة استيعاب، والبناء عند جديد وبعد حدّ أدنى."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import run_cycle  # noqa: E402

T0 = 1_000_000.0


def state(age=None, pending=False):
    return {"last_build": 0.0 if age is None else T0 - age, "pending": pending}


class TestShouldBuild(unittest.TestCase):
    def test_first_run_builds(self):
        self.assertTrue(run_cycle.should_build(state(), False, T0))

    def test_nothing_new_never_builds(self):
        self.assertFalse(run_cycle.should_build(state(age=5000), False, T0))

    def test_new_data_waits_for_minimum_interval(self):
        self.assertFalse(run_cycle.should_build(state(age=300), True, T0))
        self.assertTrue(run_cycle.should_build(state(age=900), True, T0))

    def test_slack_covers_scheduler_jitter(self):
        self.assertTrue(run_cycle.should_build(state(age=875), True, T0))
        self.assertFalse(run_cycle.should_build(state(age=860), True, T0))

    def test_pending_data_builds_once_interval_passes(self):
        self.assertFalse(run_cycle.should_build(state(age=300, pending=True), False, T0))
        self.assertTrue(run_cycle.should_build(state(age=901, pending=True), False, T0))

    def test_force_builds_anyway(self):
        self.assertTrue(run_cycle.should_build(state(age=1), False, T0, force=True))


class TestStateFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patch = mock.patch.object(run_cycle, "STATE", os.path.join(self.tmp, "cycle_state.json"))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_or_corrupt_file_means_first_run(self):
        self.assertEqual(run_cycle.load_state(), {"last_build": 0.0, "pending": False})
        with open(run_cycle.STATE, "w", encoding="utf-8") as f:
            f.write("{غير صالح")
        self.assertEqual(run_cycle.load_state(), {"last_build": 0.0, "pending": False})

    def test_round_trip(self):
        run_cycle.save_state({"last_build": 123.5, "pending": True})
        self.assertEqual(run_cycle.load_state(), {"last_build": 123.5, "pending": True})


if __name__ == "__main__":
    unittest.main()
