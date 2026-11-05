"""اختبار قرار بناء التقارير في دورة الاستيعاب: كل دقيقة استيعاب، والبناء عند جديد وبعد حدّ أدنى."""
import os
import shutil
import sys
import tempfile
import time
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
        self.assertEqual(run_cycle.load_state(), {"last_build": 0.0, "pending": False, "fp": ""})
        with open(run_cycle.STATE, "w", encoding="utf-8") as f:
            f.write("{غير صالح")
        self.assertEqual(run_cycle.load_state(), {"last_build": 0.0, "pending": False, "fp": ""})

    def test_round_trip(self):
        run_cycle.save_state({"last_build": 123.5, "pending": True})
        self.assertEqual(run_cycle.load_state(), {"last_build": 123.5, "pending": True, "fp": ""})


if __name__ == "__main__":
    unittest.main()


class TestForceOrWait(unittest.TestCase):
    """زر التحديث خلف دورة مجدولة: ينتظرها ثم يبني، أو يكتفي ببنائها، أو يعيد SKIPPED بعد المهلة."""

    def test_waits_then_builds(self):
        rcs = iter([run_cycle.SKIPPED, run_cycle.SKIPPED, 0])
        with mock.patch.object(run_cycle, "main", side_effect=lambda argv: next(rcs)) as m, \
                mock.patch.object(run_cycle, "load_state", return_value=state(age=100)):
            self.assertEqual(run_cycle.force_or_wait(t0=time.time(), timeout=60, poll=0), 0)
        self.assertEqual(m.call_count, 3)

    def test_uses_build_finished_by_other_cycle(self):
        with mock.patch.object(run_cycle, "main", return_value=run_cycle.SKIPPED) as m, \
                mock.patch.object(run_cycle, "load_state", return_value={"last_build": T0 + 5, "pending": False}):
            self.assertEqual(run_cycle.force_or_wait(t0=T0, timeout=60, poll=0), 0)
        self.assertEqual(m.call_count, 0)

    def test_gives_up_after_timeout(self):
        with mock.patch.object(run_cycle, "main", return_value=run_cycle.SKIPPED), \
                mock.patch.object(run_cycle, "load_state", return_value=state(age=100)):
            self.assertEqual(run_cycle.force_or_wait(t0=T0, timeout=0, poll=0), run_cycle.SKIPPED)


class TestHealth(unittest.TestCase):
    def test_write_health_records_ok_and_error(self):
        import json
        import tempfile
        tmp = tempfile.mkdtemp()
        orig = run_cycle.HEALTH
        run_cycle.HEALTH = os.path.join(tmp, "health.json")
        try:
            h = run_cycle.write_health(True, None, 0, 10, "ok sec 1.0")
            self.assertTrue(h["ok"] and h["ts"].endswith("Z"))
            on_disk = json.load(open(run_cycle.HEALTH, encoding="utf-8"))
            self.assertEqual(on_disk["turns_total"], 10)
            h = run_cycle.write_health(False, "KeyError", 2)
            self.assertFalse(h["ok"])
            self.assertEqual((h["error"], h["files_error"]), ("KeyError", 2))
        finally:
            run_cycle.HEALTH = orig
            shutil.rmtree(tmp, ignore_errors=True)
