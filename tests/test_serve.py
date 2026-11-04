"""اختبار الخادم المحلي: تقديم اللوحة، رفض المسارات الغريبة، وحماية /refresh من المضيف أو الأصل الغريب."""
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import run_cycle  # noqa: E402
import serve  # noqa: E402


class TestServe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "index.html"), "w", encoding="utf-8") as f:
            f.write("<p>لوحة</p>")
        with open(os.path.join(self.tmp, "hourly.html"), "w", encoding="utf-8") as f:
            f.write("<html>ساعة</html>")
        with open(os.path.join(self.tmp, "cache.html"), "w", encoding="utf-8") as f:
            f.write("<p>أدوار</p>")
        os.makedirs(os.path.join(self.tmp, "assets"))
        with open(os.path.join(self.tmp, "assets", "platform.css"), "w", encoding="utf-8") as f:
            f.write(":root{--brand:#0b6e75}")
        os.makedirs(os.path.join(self.tmp, "assets", "fonts"))
        with open(os.path.join(self.tmp, "assets", "fonts", "Inter.ttf"), "wb") as f:
            f.write(b"\x00\x01\x00\x00")
        with open(os.path.join(self.tmp, "assets", "fonts", "OFL-Inter.txt"), "w", encoding="utf-8") as f:
            f.write("ترخيص")
        with open(os.path.join(self.tmp, "report1_x.csv"), "w", encoding="utf-8") as f:
            f.write("a,b\n1,2\n")
        with open(os.path.join(self.tmp, "secret.txt"), "w", encoding="utf-8") as f:
            f.write("لا يُقدَّم")
        self.calls = []
        self.rc = 0
        self.ops = []
        self.srv = serve.make_server(0, self.tmp, lambda t0: self.calls.append(t0) or self.rc,
                                     lambda: [{"ts": "2026-10-30T10:00:00Z", "f": 1.0, "src": "cli_usage"}],
                                     lambda op, p: self.ops.append((op, p)) or {"ok": True, "op": op, "files": 3})
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def req(self, method, path, headers=None, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": "127.0.0.1:%d" % self.port}
        h.update(headers or {})
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, body

    def test_serves_dashboard_and_csv_only(self):
        self.assertEqual(self.req("GET", "/")[0], 200)
        self.assertIn("لوحة".encode(), self.req("GET", "/index.html")[1])
        self.assertEqual(self.req("GET", "/report1_x.csv")[0], 200)
        self.assertEqual(self.req("GET", "/cache.html")[0], 301)  # الصفحة القديمة تُحوَّل إلى قسمها
        code, css = self.req("GET", "/assets/platform.css")
        self.assertEqual(code, 200)
        self.assertIn(b"--brand", css)
        self.assertEqual(self.req("GET", "/assets/../secret.txt")[0], 404)
        for bad in ("/secret.txt", "/../x", "/report1_x.csv/../secret.txt", "/%2e%2e/secret.txt"):
            self.assertEqual(self.req("GET", bad)[0], 404, bad)

    def test_serves_only_ttf_fonts(self):
        code, body = self.req("GET", "/assets/fonts/Inter.ttf")
        self.assertEqual((code, body[:2]), (200, b"\x00\x01"))
        for bad in ("/assets/fonts/OFL-Inter.txt", "/assets/fonts/missing.ttf", "/assets/fonts/../../secret.txt", "/assets/fonts/%2e%2e/secret.txt"):
            self.assertEqual(self.req("GET", bad)[0], 404, bad)

    def test_refresh_runs_cycle_for_own_host(self):
        code, body = self.req("POST", "/refresh")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["ok"])
        self.assertEqual(len(self.calls), 1)

    def test_refresh_reports_busy_when_another_cycle_holds_the_lock(self):
        """الدورة المجدولة تحمل القفل حتى انقضاء المهلة: الجواب busy لا ok (لا إعادة تحميل لصفحة قديمة)."""
        self.rc = run_cycle.SKIPPED
        code, body = self.req("POST", "/refresh")
        j = json.loads(body)
        self.assertEqual((code, j["ok"], j["busy"]), (200, False, True))
        self.assertAlmostEqual(self.calls[-1], time.time(), delta=5)  # لحظة الطلب تُمرَّر إلى الدورة

    def test_storage_endpoints_pass_json_and_guard_host(self):
        """أدوات حجم البيانات: JSON في الجسم إلى الدالة المحقونة، 404 لعملية مجهولة، 403 لمضيف غريب، 400 لجسم غير صالح."""
        code, body = self.req("POST", "/storage/plan", body=json.dumps({"group": "file_history", "days": 30}).encode())
        self.assertEqual((code, json.loads(body)["files"]), (200, 3))
        self.assertEqual(self.ops[-1], ("plan", {"group": "file_history", "days": 30}))
        self.assertEqual(self.req("POST", "/storage/delete")[0], 404)
        self.assertEqual(self.req("POST", "/storage/apply", {"Host": "evil.example"})[0], 403)
        self.assertEqual(self.req("POST", "/storage/apply", body=b"[1,2]")[0], 400)
        self.assertEqual(self.req("GET", "/storage/plan")[0], 404)

    def test_refresh_rejects_foreign_host_or_origin(self):
        self.assertEqual(self.req("POST", "/refresh", {"Host": "evil.example"})[0], 403)
        self.assertEqual(self.req("POST", "/refresh", {"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.req("POST", "/refresh", {"Origin": "http://127.0.0.1:%d" % self.port})[0], 200)
        self.assertEqual(len(self.calls), 1)

    def test_plan_json_is_live_and_local_only(self):
        code, body = self.req("GET", "/plan.json")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body), [{"ts": "2026-10-30T10:00:00Z", "f": 1.0, "src": "cli_usage"}])
        self.assertEqual(self.req("GET", "/plan.json", {"Host": "evil.example"})[0], 403)

    def test_get_does_not_trigger_refresh(self):
        self.req("GET", "/refresh")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
