"""حارس الخادم: يضمن أن خادم ميزان (127.0.0.1:8790) يعمل بالكود الحالي.

المشكلة: الخادم يحمل كوده في الذاكرة، فبعد أي تحديث يبقى يقدّم القائمة والصفحات القديمة (ويردّ «غير موجودة» للصفحات الجديدة)
حتى يُعاد تشغيله يدويًّا. الحل: يكتب الخادم عند بدئه بصمة الكود في data/serve_state.json، وتفحصها الدورة المجدولة (كل دقيقة):
إن اختلفت البصمة أو غاب الملف (خادم قديم) أوقفت العملية المستمعة على المنفذ وشغّلت خادمًا جديدًا بلا نافذة.
لا يعمل إلا في ويندوز، ولا يبدأ خادمًا لم يكن شغّالًا (من أوقفه بيده يبقى موقوفًا). أرقام وعمليات فقط، بلا نصوص.
"""
import hashlib
import json
import os
import subprocess
import sys

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
STATE = os.path.join(ROOT, "data", "serve_state.json")
PORT = 8790
EXTS = (".py", ".html", ".css", ".js")


def fingerprint():
    """بصمة الكود: أسماء ملفات src وأحجامها ووقت تعديلها (تتغيّر بأي تحديث)."""
    h = hashlib.sha1()
    for base, dirs, files in os.walk(SRC):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__" and d != "fonts")
        for f in sorted(files):
            if f.endswith(EXTS):
                st = os.stat(os.path.join(base, f))
                h.update(("%s/%s:%d:%d;" % (os.path.relpath(base, SRC), f, st.st_size, st.st_mtime_ns // 1_000_000_000)).encode())
    return h.hexdigest()


def write_state(port, pid=None):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"pid": pid or os.getpid(), "port": port, "fp": fingerprint()}, f)


def read_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            s = json.load(f)
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def listener_pid(port, netstat_text):
    """رقم العملية المستمعة على 127.0.0.1:port من خرج netstat -ano (None إن لم توجد)."""
    for ln in netstat_text.splitlines():
        p = ln.split()
        if len(p) >= 5 and p[0].upper() == "TCP" and p[2].endswith(":0") and p[1].rsplit(":", 1)[-1] == str(port):  # المستمِع: العنوان البعيد :0 (كلمة الحالة تتغيّر بلغة ويندوز)
            try:
                return int(p[4])
            except ValueError:
                return None
    return None


PS_FIND = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'serve\\.py' -and $_.Name -match 'python' } "
           "| ForEach-Object { $_.ProcessId }")


def server_pids(port, netstat_text):
    """عمليات الخادم: المستمِعة على المنفذ، وإلا كل عملية بايثون سطر أمرها serve.py (يعمل مع أي لغة ويندوز)."""
    pid = listener_pid(port, netstat_text)
    if pid:
        return [pid]
    r = subprocess.run(["powershell", "-NoProfile", "-Command", PS_FIND], capture_output=True, text=True, timeout=30,
                       stdin=subprocess.DEVNULL, creationflags=0x08000000)
    return [int(x) for x in r.stdout.split() if x.isdigit() and int(x) != os.getpid()]


def is_stale(state, fp):
    return state.get("fp") != fp


def note(msg):
    """آخر نتيجة للحارس في ملف صغير (للتشخيص؛ بلا نصوص مستخدم)."""
    try:
        with open(os.path.join(ROOT, "data", "serve_guard.txt"), "w", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def ensure(port=PORT):
    """يعيد تشغيل الخادم إن كان شغّالًا بكود قديم. يعيد 'fresh' أو 'restarted' أو 'none' (لا خادم) أو 'skip'."""
    if os.name != "nt":
        return "skip"
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL,
                             creationflags=0x08000000).stdout
        pids = server_pids(port, out)
        pid = pids[0] if pids else None
        if pid is None:
            note("none: no listener on %d; lines with port: %r; total lines %d" % (port, [l.strip() for l in out.splitlines() if ":%d " % port in l and "TIME_WAIT" not in l and "ESTAB" not in l][:6], len(out.splitlines())))
            return "none"
        if not is_stale(read_state(), fingerprint()) and read_state().get("pid") in pids:
            return "fresh"
        for q in pids:
            subprocess.run(["taskkill", "/F", "/PID", str(q)], capture_output=True, timeout=15, stdin=subprocess.DEVNULL, creationflags=0x08000000)
        note("restarted pids %s" % pids)
        exe = sys.executable
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        subprocess.Popen([w if os.path.exists(w) else exe, os.path.join(SRC, "serve.py"), "--port", str(port)], cwd=ROOT,
                         creationflags=0x00000008 | 0x00000200 | 0x08000000, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "restarted"
    except Exception as exc:  # noqa: BLE001 — الحارس لا يوقف الدورة
        note(type(exc).__name__ + " " + str(exc)[:120])
        return "skip"
