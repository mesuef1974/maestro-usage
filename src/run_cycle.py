"""دورة تشغيل دورية واحدة: تحميل السجلات ثم spool الـstatusLine، ونسخة احتياطية يومية. تُستدعى من المهمة المجدولة.

أرقام فقط في data\\cycle.log. قفل بسيط يمنع تداخل دورتين: main تعيد SKIPPED حين تعمل دورة أخرى (المجدول يراها 0)،
وزر «تحديث فوري» يستعمل force_or_wait فينتظر تلك الدورة بدل إعادة الصفحة القديمة بـok كاذب. لا يرمي استثناءً إلى المجدول (يسجّل الخطأ).
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backup_db  # noqa: E402
import import_external  # noqa: E402
import reports  # noqa: E402
import rollups  # noqa: E402
import statusline_loader  # noqa: E402
import storage_scan  # noqa: E402
import usage_db  # noqa: E402
import usage_ingest  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
LOCK = os.path.join(DATA, "cycle.lock")
LOG = os.path.join(DATA, "cycle.log")
LOG_MAX = 500_000
LOCK_STALE_SECONDS = 1800
SKIPPED = 3  # رمز رجوع main حين تحمل دورة أخرى القفل (ليس خطأ؛ المجدول يحوّله إلى 0)
WAIT_TIMEOUT_SEC = 240  # أقصى انتظار لزر التحديث خلف دورة مجدولة (بناء التقارير قد يطول عند الضغط)
STATE = os.path.join(DATA, "cycle_state.json")  # آخر بناء للتقارير وهل بقيت بيانات جديدة لم تُبنَ بعد
BUILD_MIN_SEC = 900  # الاستيعاب كل دقيقة، والتقارير على الأقل كل 15 دقيقة وعند وجود جديد
BUILD_SLACK_SEC = 30  # اهتزاز المجدول: دورة تأتي قبل الحدّ بثوانٍ لا تُؤجَّل دقيقة كاملة


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


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            s = json.load(f)
        return {"last_build": float(s.get("last_build", 0)), "pending": bool(s.get("pending", False))}
    except (OSError, ValueError, TypeError):
        return {"last_build": 0.0, "pending": False}


def save_state(state):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, STATE)


def should_build(state, new_data, now, force=False):
    """يُبنى التقرير إذا فُرض، أو لم يُبنَ قط، أو وُجدت بيانات جديدة (الآن أو معلّقة) ومضى حدّ أدنى على آخر بناء."""
    if force or not state["last_build"]:
        return True
    if not (new_data or state["pending"]):
        return False
    return now - state["last_build"] >= BUILD_MIN_SEC - BUILD_SLACK_SEC


def main(argv=None):
    force = "--force" in (argv if argv is not None else sys.argv[1:])
    if not acquire():
        log("skipped: another cycle is running")
        return SKIPPED
    try:
        t = time.time()
        con = usage_db.connect()
        st = usage_ingest.run(con)
        ext = import_external.run_dir(con)  # جلسات سحابية مصدَّرة أرقامًا فقط إلى data/external
        sp = statusline_loader.load_spool(con)
        new_data = bool(ext or st["turns_new"] or st["turns_updated"] or st["turns_reassigned"] or sp.get("plans_new"))
        if new_data:
            rollups.refresh(con)  # تجميعات الاستهلاك تتبع كل بيانات جديدة (تُعاد كتابتها كاملةً في معاملة)
        sc = {}
        sg = storage_scan.run(con)  # حجم ~/.claude كل ساعة؛ صفر توكنات
        state = load_state()
        rep = "skipped"
        if should_build(state, new_data, t, force):
            try:
                t2 = time.time()
                reports.build(con)  # يُولّد reports\index.html وملفات CSV؛ فشله لا يوقف الدورة
                rep = "ok sec %.1f" % (time.time() - t2)
                state = {"last_build": time.time(), "pending": False}
            except Exception as exc:  # noqa: BLE001
                rep = "ERROR " + type(exc).__name__
                state["pending"] = True
        else:
            state["pending"] = state["pending"] or new_data
        save_state(state)
        con.close()
        if new_data or sc.get("config_changed") or sg.get("scanned") or st["files_error"] or rep != "skipped" or force:  # دورة بلا جديد ولا بناء لا تُسجَّل (كل دقيقة)
            log("ingest " + json.dumps({k: st[k] for k in ("files_ingested", "turns_new", "turns_updated", "turns_reassigned", "files_error", "turns_total")})
                + " spool " + json.dumps(sp) + " startup " + json.dumps(sc) + " storage " + json.dumps(sg)
                + " reports " + rep + " sec %.1f" % (time.time() - t))
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


def force_or_wait(t0=None, timeout=WAIT_TIMEOUT_SEC, poll=2.0):
    """بناء قسري لزر التحديث. إن كانت دورة أخرى تعمل ننتظرها (حتى timeout) ثم نبني؛ وإن بنت هي التقارير بعد لحظة الطلب t0
    اكتفينا بها (طلبات متراكمة خلف قفل الخادم لا تبني مرتين). يعيد 0 عند النجاح وSKIPPED عند انقضاء المهلة."""
    t0 = time.time() if t0 is None else t0
    while True:
        if load_state()["last_build"] >= t0:
            return 0
        rc = main(["--force"])
        if rc != SKIPPED:
            return rc
        if time.time() - t0 >= timeout:
            return SKIPPED
        time.sleep(poll)


if __name__ == "__main__":
    rc = main()
    sys.exit(0 if rc == SKIPPED else rc)
