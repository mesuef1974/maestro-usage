"""اختبار الخادم المحلي: تقديم اللوحة، رفض المسارات الغريبة، وحماية /refresh من المضيف أو الأصل الغريب."""
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import serve  # noqa: E402


class TestServe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "index.html"), "w", encoding="utf-8") as f:
            f.write("<p>لوحة</p>")
        with open(os.path.join(self.tmp, "hourly.html"), "w", encoding="utf-8") as f:
            f.write("<html>ساعة</html>")
        with open(os.path.join(self.tmp, "roles.html"), "w", encoding="utf-8") as f:
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
        self.srv = serve.make_server(0, self.tmp, lambda: self.calls.append(1) or 0)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def req(self, method, path, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": "127.0.0.1:%d" % self.port}
        h.update(headers or {})
        c.request(method, path, headers=h)
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, body

    def test_serves_dashboard_and_csv_only(self):
        self.assertEqual(self.req("GET", "/")[0], 200)
        self.assertIn("لوحة".encode(), self.req("GET", "/index.html")[1])
        self.assertEqual(self.req("GET", "/report1_x.csv")[0], 200)
        self.assertIn("أدوار".encode(), self.req("GET", "/roles.html")[1])
        code, css = self.req("GET", "/assets/platform.css")
        self.assertEqual(code, 200)
        self.assertIn(b"--brand", css)
        self.assertEqual(self.req("GET", "/assets/../secret.txt")[0], 404)
        self.assertIn("ساعة".encode(), self.req("GET", "/hourly.html")[1])
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

    def test_refresh_rejects_foreign_host_or_origin(self):
        self.assertEqual(self.req("POST", "/refresh", {"Host": "evil.example"})[0], 403)
        self.assertEqual(self.req("POST", "/refresh", {"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.req("POST", "/refresh", {"Origin": "http://127.0.0.1:%d" % self.port})[0], 200)
        self.assertEqual(len(self.calls), 1)

    def test_get_does_not_trigger_refresh(self):
        self.req("GET", "/refresh")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
