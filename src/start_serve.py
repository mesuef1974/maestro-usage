"""مُطلق ميزان عند الدخول إلى ويندوز (مهمة SchoolOS-Mizan-AtLogon): يشغّل serve.py بلا نافذة ولا يكرّر نسخةً إن كان المنفذ مشغولًا.
أمر المالك 2026-11-07. يُشغَّل بـpythonw؛ الأثر في data/start_serve.log لا في نافذة."""
import datetime
import os
import socket
import subprocess
import sys

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
PORT = 8790
LOG = os.path.join(ROOT, "data", "start_serve.log")


def listening(port: int = PORT) -> bool:
    with socket.socket() as s:
        s.settimeout(1.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def log(msg: str) -> None:
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}\n")


def main() -> int:
    if listening():
        log(f"المنفذ {PORT} مشغول: لا نسخة ثانية")
        return 0
    py = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    py = py if os.path.isfile(py) else sys.executable
    subprocess.Popen([py, os.path.join(SRC, "serve.py"), "--port", str(PORT)], cwd=ROOT, creationflags=0x08000000 | 0x00000008,  # NO_WINDOW | DETACHED
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log(f"بدأ الخادم على {PORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
