"""يلتقط تشغيلات الجلسات الحيّة من `claude agents --json --all` (بلا استدعاء للنموذج: صفر توكنات) في agent_starts.

startedAt هو وقت بدء العملية لا إنشاء الجلسة؛ تغيّره لجلسة معروفة يعني إعادة تشغيل، وعندها يُعاد قراءة autoCompactWindow.
القائمة تضمّ الجلسات الحيّة فقط، فالسجل يبدأ من أول التقاط ولا يمتد إلى الماضي. يُحفظ الرقم (4 أرقام) لا اسم الجلسة.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_db  # noqa: E402

MIN_INTERVAL_SEC = 300
TIMEOUT_SEC = 30
NUMBER_RX = re.compile(r"^(\d{4})\b")
KIND_RX = re.compile(r"^[a-z_\-]{1,30}$")
ID_RX = re.compile(r"[A-Za-z0-9_\-:.]{1,100}")


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse(text):
    """نصّ JSON ← صفوف (session_id, started_at, number, kind, pid)؛ ما لا يطابق الشكل المتوقع يُتجاهل."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    rows = []
    for r in data if isinstance(data, list) else []:
        if not isinstance(r, dict):
            continue
        sid, started = r.get("sessionId"), r.get("startedAt")
        if not isinstance(sid, str) or not ID_RX.fullmatch(sid) or not isinstance(started, (int, float)) or isinstance(started, bool):
            continue
        m = NUMBER_RX.match(r.get("name") or "")
        kind = r.get("kind")
        pid = r.get("pid")
        rows.append((sid, _iso(started), m.group(1) if m else None,
                     kind if isinstance(kind, str) and KIND_RX.match(kind) else None,
                     pid if isinstance(pid, int) and not isinstance(pid, bool) else None))
    return rows


def record(con, rows, now=None):
    """upsert بتكرار آمن؛ يعيد (صفوف جديدة، أرقام جلسات رُبطت)."""
    now = now or usage_db.now_iso()
    new = linked = 0
    for sid, started, number, kind, pid in rows:
        new += con.execute("SELECT COUNT(*) FROM agent_starts WHERE session_id=? AND started_at=?", (sid, started)).fetchone()[0] == 0
        con.execute(
            "INSERT INTO agent_starts(session_id, started_at, number, kind, pid, first_seen, last_seen) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(session_id, started_at) DO UPDATE SET last_seen=excluded.last_seen, "
            "number=COALESCE(excluded.number, agent_starts.number), kind=COALESCE(excluded.kind, agent_starts.kind), pid=COALESCE(excluded.pid, agent_starts.pid)",
            (sid, started, number, kind, pid, now, now))
        if number:  # رقم احتياطي فقط حيث لا رقم من العنوان المخزَّن في السجل ولا من التطبيق
            linked += con.execute("UPDATE sessions SET number=?, number_source='agents' WHERE session_key=? AND number IS NULL",
                                  (number, sid)).rowcount
    con.commit()
    return new, linked


def due(con, now=None):
    last = con.execute("SELECT MAX(last_seen) FROM agent_starts").fetchone()[0]
    if not last:
        return True
    now = now or datetime.now(timezone.utc)
    return (now - datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds() >= MIN_INTERVAL_SEC - 30


def fetch():
    exe = shutil.which("claude") or os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run([exe, "agents", "--json", "--all"], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       encoding="utf-8", timeout=TIMEOUT_SEC, creationflags=flags)
    return r.stdout


def run(con, fetch_fn=None, now=None):
    """يلتقط إن حان الموعد؛ يعيد dict بأرقام فقط، ولا يرمي إلى الدورة."""
    if not due(con, now):
        return {"agents": "skipped"}
    try:
        rows = parse((fetch_fn or fetch)())
    except (OSError, subprocess.SubprocessError):
        return {"agents": "fail"}
    if not rows:
        return {"agents": "empty"}
    new, linked = record(con, rows)
    return {"agents": len(rows), "agents_new": new, "numbers_linked": linked}


def health(con, now=None):
    """أرقام فحص صحة الالتقاط: عدد التشغيلات والجلسات وإعادات التشغيل وعمر آخر التقاط (ثوانٍ) والحيّ منها."""
    now = now or datetime.now(timezone.utc)
    runs, sessions, last = con.execute("SELECT COUNT(*), COUNT(DISTINCT session_id), MAX(last_seen) FROM agent_starts").fetchone()
    restarts = runs - sessions
    age = None if not last else int((now - datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds())
    live = con.execute("SELECT COUNT(*) FROM agent_starts WHERE last_seen=?", (last,)).fetchone()[0] if last else 0
    return {"runs": runs, "sessions": sessions, "restarts": restarts, "last_capture_age_sec": age, "live_at_last_capture": live,
            "healthy": age is not None and age <= 3 * MIN_INTERVAL_SEC}


if __name__ == "__main__":
    c = usage_db.connect()
    print(health(c) if "--health" in sys.argv[1:] else run(c))
