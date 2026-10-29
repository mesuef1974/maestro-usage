"""دورة تشغيل دورية واحدة: تحميل السجلات ثم spool الـstatusLine، ونسخة احتياطية يومية. تُستدعى من المهمة المجدولة.

أرقام فقط في data\\cycle.log. قفل بسيط يمنع تداخل دورتين. لا يرمي استثناءً إلى المجدول (يسجّل الخطأ).
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backup_db  # noqa: E402
import reports  # noqa: E402
import statusline_loader  # noqa: E402
import usage_db  # noqa: E402
import usage_ingest  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
LOCK = os.path.join(DATA, "cycle.lock")
LOG = os.path.join(DATA, "cycle.log")
LOG_MAX = 500_000
LOCK_STALE_SECONDS = 1800


def log(msg):
    os.makedirs(DATA, exist_ok=True)
    if os.path.exists(LOG) and os.path.getsize(LOG) > LOG_MAX:
        os.replace(LOG, LOG + ".old")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(datetime.now().strftime("%Y-%m-%dT%H:%M:%S ") + msg + "\n")


def acquire():
    os.makedirs(DATA, exist_ok=True)
    if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < LOCK_STALE_SECONDS:
        return False
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))
    return True


def backup_due():
    d = backup_db.BACKUP_DIR
    if not d.exists():
        return True
    newest = max((p.stat().st_mtime for p in d.glob("flow_usage_*.sqlite3")), default=0)
    return time.time() - newest > timedelta(hours=24).total_seconds()


def main():
    if not acquire():
        log("skipped: another cycle is running")
        return 0
    try:
        t = time.time()
        con = usage_db.connect()
        st = usage_ingest.run(con)
        sp = statusline_loader.load_spool(con)
        try:
            t2 = time.time()
            reports.build(con)  # يُولّد reports\index.html وملفات CSV؛ فشله لا يوقف الدورة
            rep = "ok sec %.1f" % (time.time() - t2)
        except Exception as exc:  # noqa: BLE001
            rep = "ERROR " + type(exc).__name__
        con.close()
        log("ingest " + json.dumps({k: st[k] for k in ("files_ingested", "turns_new", "turns_updated", "turns_reassigned", "files_error", "turns_total")})
            + " spool " + json.dumps(sp) + " reports " + rep + " sec %.1f" % (time.time() - t))
        if backup_due():
            dest, res = backup_db.backup()
            log("backup integrity_check=" + res)
    except Exception as exc:  # noqa: BLE001 — المجدول لا يجب أن يفشل بصمت
        log("ERROR " + type(exc).__name__)
        return 1
    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
