"""خادم محلي اختياري للّوحة: يقدّم reports\\index.html ويشغّل دورة تحميل فورية عند ضغط «تحديث فوري».

يربط 127.0.0.1 فقط، ولا يعمل إلا ما تشغّله بيدك (ليس مهمة دائمة). التشغيل: python src\\serve.py [--port 8790]
المسارات: GET / وكل صفحة في pages.PAGES، GET /assets/platform.css (الأسلوب المركزي)، GET /reportN_*.csv (ملفات التقارير)، POST /refresh (دورة تحميل ثم JSON).
"""
import argparse
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hourly_page  # noqa: E402
import pages  # noqa: E402
import reports  # noqa: E402
import run_cycle  # noqa: E402
import usage_db  # noqa: E402

PAGES = {"/": "index.html", "/sessions.html": "roles.html", **{"/" + p["file"]: p["file"] for p in pages.PAGES}}  # من سجلّ الصفحات
CSV_RE = re.compile(r"^/(report\d_[a-z_]+\.csv)$")


def live_plan():
    """لقطات الحصة من القاعدة مباشرةً (أرقام فقط)، دون انتظار إعادة بناء الصفحات."""
    con = usage_db.connect()
    try:
        return hourly_page.plan_rows(con)
    finally:
        con.close()


def make_server(port, reports_dir=None, refresh_fn=None, plan_fn=None):
    reports_dir = reports_dir or reports.REPORTS_DIR
    refresh_fn = refresh_fn or (lambda: run_cycle.main(["--force"]))  # زر التحديث يفرض بناء التقارير
    plan_fn = plan_fn or live_plan
    lock = threading.Lock()  # دورة واحدة في وقت واحد

    class Handler(BaseHTTPRequestHandler):
        server_version = "MaestroUsage"

        def log_message(self, *a):  # بلا سجلات (لا تلوّث الطرفية)
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self):
            host = (self.headers.get("Host") or "").lower()
            origin = self.headers.get("Origin")
            own = {"127.0.0.1:%d" % self.server.server_address[1], "localhost:%d" % self.server.server_address[1]}
            return host in own and (origin is None or origin.split("://", 1)[-1].lower() in own)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/favicon.ico":  # يمنع خطأ 404 في وحدة تحكم المتصفح
                return self._send(204, b"", "image/x-icon")
            if path == "/plan.json":
                if not self._host_ok():  # كبقية الواجهات: مضيف محلي فقط
                    return self._send(403, b"forbidden", "text/plain; charset=utf-8")
                body = json.dumps(plan_fn(), ensure_ascii=False).encode("utf-8")
                return self._send(200, body, "application/json")
            if path in PAGES:
                name, ctype = PAGES[path], "text/html; charset=utf-8"
            elif path == "/assets/platform.css":
                name, ctype = "assets/platform.css", "text/css; charset=utf-8"
            else:
                m = CSV_RE.match(path)
                if not m:
                    return self._send(404, b"not found", "text/plain; charset=utf-8")
                name, ctype = m.group(1), "text/csv; charset=utf-8"
            try:
                with open(os.path.join(reports_dir, name), "rb") as f:
                    body = f.read()
            except OSError:
                return self._send(404, b"not found", "text/plain; charset=utf-8")
            self._send(200, body, ctype)

        def do_POST(self):
            if self.path.split("?", 1)[0] != "/refresh":
                return self._send(404, b"not found", "text/plain; charset=utf-8")
            if not self._host_ok():  # يمنع صفحة غريبة من تشغيل الدورة عبر المتصفح
                return self._send(403, b"forbidden", "text/plain; charset=utf-8")
            t = time.time()
            with lock:
                rc = refresh_fn()
            body = json.dumps({"ok": rc == 0, "seconds": round(time.time() - t, 1)}).encode("utf-8")
            self._send(200, body, "application/json")

    class Server(ThreadingHTTPServer):
        allow_reuse_address = False  # في ويندوز يسمح SO_REUSEADDR بخادمين على المنفذ نفسه فيردّ أقدمهما بكود قديم

    return Server(("127.0.0.1", port), Handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8790)
    a = ap.parse_args(argv)
    srv = make_server(a.port)
    print("http://127.0.0.1:%d/  (Ctrl+C للإيقاف)" % a.port, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
