"""صفحة «المشغّل الحيّ»: مسجّلة بعد «رسم الأتمتة» في الحوكمة، تُبنى بالغلاف الموحّد، ونقطة بياناتها /runner.json حيّة ومحلّيّة فقط."""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pages  # noqa: E402
import runner_page  # noqa: E402
import serve  # noqa: E402


class RunnerPageTest(unittest.TestCase):
    def test_registered_right_after_flow_in_governance(self):
        files = [p["file"] for p in pages.PAGES]
        self.assertEqual(files[files.index("flow.html") + 1], "runner.html")
        self.assertEqual(pages.BY_FILE["runner.html"]["group"], "الحوكمة")

    def test_render_uses_shell_and_live_api(self):
        page = runner_page.render(runner_page.payload(), "2026-11-04 15:00")
        self.assertIn('href="runner.html" aria-current="page"', page)
        for token in ("__SHELL_", "__DATA__", "__LIB__", "__PAGEHEAD__", "<!--@"):
            self.assertNotIn(token, page)
        self.assertIn("fetch(API", page)
        self.assertIn('"api":"runner.json"', page)


class RunnerJsonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.calls = 0

        def fake():
            self.calls += 1
            return {"ok": True, "n": self.calls}

        self.srv = serve.make_server(0, reports_dir=self.tmp.name, runner_fn=fake)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def req(self, path, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", path, headers=headers or {})
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, body

    def test_live_each_request_and_local_only(self):
        code, body = self.req("/runner.json")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["n"], 1)
        self.assertEqual(json.loads(self.req("/runner.json")[1])["n"], 2)  # لا تخزين: لقطة جديدة كلّ طلب
        self.assertEqual(self.req("/runner.json", {"Host": "evil.example"})[0], 403)

    def test_source_failure_is_503_not_crash(self):
        def boom():
            raise OSError("لا دفتر")

        srv = serve.make_server(0, reports_dir=self.tmp.name, runner_fn=boom)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("GET", "/runner.json")
            r = c.getresponse()
            self.assertEqual(r.status, 503)
            self.assertFalse(json.loads(r.read())["ok"])
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
