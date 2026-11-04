"""خادم محلي اختياري للّوحة: يقدّم reports\\index.html ويشغّل دورة تحميل فورية عند ضغط «تحديث فوري».

يربط 127.0.0.1 فقط، ولا يعمل إلا ما تشغّله بيدك (ليس مهمة دائمة). التشغيل: python src\\serve.py [--port 8790]
المسارات: GET / وكل صفحة في pages.PAGES، GET /assets/platform.css (الأسلوب المركزي)، GET /reportN_*.csv (ملفات التقارير)، POST /refresh (دورة تحميل ثم JSON)،
POST /storage/{scan|plan|apply|restore|purge} (أدوات حجم البيانات؛ التغييرات تتطلّب confirm=true).
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
import request_page  # noqa: E402
import run_cycle  # noqa: E402
import runner_page  # noqa: E402
import storage_scan  # noqa: E402
import usage_db  # noqa: E402

PAGES = {"/": "index.html", "/sessions.html": "roles.html", **{"/" + p["file"]: p["file"] for p in pages.PAGES}}  # من سجلّ الصفحات
FONT_RE = re.compile(r"^/assets/fonts/[A-Za-z]+\.ttf$")
CSV_RE = re.compile(r"^/(report\d_[a-z_]+\.csv)$")


def live_plan():
    """لقطات الحصة من القاعدة مباشرةً (أرقام فقط)، دون انتظار إعادة بناء الصفحات."""
    con = usage_db.connect()
    try:
        return hourly_page.plan_rows(con)
    finally:
        con.close()


STORAGE_RE = re.compile(r"^/storage/(scan|plan|apply|restore|purge)$")


def live_storage(op, params):
    """أدوات حجم البيانات على اتصال خاص؛ بعد أي تغيير يُعاد المسح فورًا كي تعكسه الصفحة عند إعادة البناء."""
    con = usage_db.connect()
    try:
        out = storage_scan.handle(op, params, con)
        if op in ("apply", "restore", "purge"):
            out["rescan"] = storage_scan.run(con, force=True)
        return out
    finally:
        con.close()


def make_server(port, reports_dir=None, refresh_fn=None, plan_fn=None, storage_fn=None, runner_fn=None):
    reports_dir = reports_dir or reports.REPORTS_DIR
    storage_fn = storage_fn or live_storage
    refresh_fn = refresh_fn or run_cycle.force_or_wait  # زر التحديث يفرض البناء وينتظر دورة مجدولة إن كانت تعمل؛ يأخذ لحظة الطلب
    plan_fn = plan_fn or live_plan
    runner_fn = runner_fn or runner_page.snapshot  # «المشغّل الحيّ»: لقطة الدفتر عند كلّ طلب (تقرأ فقط)
    lock = threading.Lock()  # دورة واحدة في وقت واحد
    request_rate = request_page.RateLimit(request_page.RATE_PER_HOUR)

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
            if path == "/runner.json":
                if not self._host_ok():
                    return self._send(403, b"forbidden", "text/plain; charset=utf-8")
                try:
                    out, code = runner_fn(), 200
                except Exception as exc:  # noqa: BLE001 — مصدر خارجيّ (دفتر مجلّد المدير): لا يُسقط الخادم
                    out, code = {"ok": False, "error": str(exc)[:200]}, 503
                return self._send(code, json.dumps(out, ensure_ascii=False).encode("utf-8"), "application/json")
            if path in PAGES:
                name, ctype = PAGES[path], "text/html; charset=utf-8"
            elif path == "/assets/platform.css":
                name, ctype = "assets/platform.css", "text/css; charset=utf-8"
            elif FONT_RE.match(path):
                name, ctype = path[1:], "font/ttf"
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

        def _json(self, code, out):
            self._send(code, json.dumps(out, ensure_ascii=False).encode("utf-8"), "application/json")

        def _origin_strict_ok(self):
            """كلّ POST: Host وOrigin معاً من القائمة البيضاء؛ غيابُ Origin يُرفض (المتصفّح يرسله دائماً مع POST)."""
            origin = self.headers.get("Origin")
            port = self.server.server_address[1]
            own = {"127.0.0.1:%d" % port, "localhost:%d" % port}
            return self._host_ok() and origin is not None and origin.split("://", 1)[-1].lower() in own

        def _post_request(self):
            if not self._origin_strict_ok():
                return self._json(403, {"error": "مصدر الطلب غير مسموح", "field": ""})
            if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
                return self._json(415, {"error": "نوع المحتوى يجب أن يكون application/json", "field": ""})
            raw_len = self.headers.get("Content-Length")
            if raw_len is None:
                return self._json(411, {"error": "طول المحتوى مطلوب", "field": ""})
            try:
                n = int(raw_len)
            except ValueError:
                return self._json(400, {"error": "طول المحتوى غير صالح", "field": ""})
            if n > request_page.MAX_BODY:
                return self._json(413, {"error": "الطلب أكبر من الحد المسموح", "field": ""})
            if not request_rate.allow():
                return self._json(429, {"error": "عدد الطلبات تجاوز الحد في الساعة", "field": ""})
            try:
                params = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                if not isinstance(params, dict):
                    raise request_page.ValidationError("جسم غير صالح", "")
                return self._json(200, request_page.submit(params))
            except request_page.ValidationError as exc:
                return self._json(400, {"error": str(exc)[:200], "field": exc.field})
            except (ValueError, OSError) as exc:
                return self._json(400, {"error": str(exc)[:200], "field": ""})

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path == "/request":  # استمارة «طلب جديد»: تكتب ملفاً في requests/ فقط، بلا نموذج
                return self._post_request()
            m = STORAGE_RE.match(path)
            if path != "/refresh" and not m:
                return self._send(404, b"not found", "text/plain; charset=utf-8")
            if not self._host_ok():  # يمنع صفحة غريبة من تشغيل الدورة أو أدوات الحجر عبر المتصفح
                return self._send(403, b"forbidden", "text/plain; charset=utf-8")
            if m:  # أدوات حجم البيانات: JSON صغير في الجسم؛ التغييرات تحت قفل الدورة نفسه
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    params = json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
                    if not isinstance(params, dict):
                        raise ValueError("جسم غير صالح")
                    with lock:
                        out = storage_fn(m.group(1), params)
                    code = 200
                except (ValueError, OSError) as exc:
                    out, code = {"ok": False, "error": str(exc)[:200]}, 400
                return self._send(code, json.dumps(out, ensure_ascii=False).encode("utf-8"), "application/json")
            t = time.time()
            with lock:  # طلب متراكم خلف قفل الخادم يأخذ لحظته الأصلية فيكتفي ببناء سبقه
                rc = refresh_fn(t)
            body = json.dumps({"ok": rc == 0, "busy": rc == run_cycle.SKIPPED, "seconds": round(time.time() - t, 1)}).encode("utf-8")
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
