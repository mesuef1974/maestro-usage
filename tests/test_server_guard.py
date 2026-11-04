import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import server_guard  # noqa: E402

NS = """  TCP    127.0.0.1:8790         0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:8790         127.0.0.1:50000        ESTABLISHED     4242
  TCP    0.0.0.0:8791           0.0.0.0:0              LISTENING       77
"""


class TestServerGuard(unittest.TestCase):
    def test_listener_pid(self):
        self.assertEqual(server_guard.listener_pid(8790, NS), 4242)
        self.assertEqual(server_guard.listener_pid(8791, NS), 77)
        self.assertIsNone(server_guard.listener_pid(9999, NS))

    def test_stale_when_missing_or_different(self):
        fp = server_guard.fingerprint()
        self.assertTrue(server_guard.is_stale({}, fp))
        self.assertTrue(server_guard.is_stale({"fp": "x"}, fp))
        self.assertFalse(server_guard.is_stale({"fp": fp}, fp))

    def test_fingerprint_stable(self):
        self.assertEqual(server_guard.fingerprint(), server_guard.fingerprint())


if __name__ == "__main__":
    unittest.main()
