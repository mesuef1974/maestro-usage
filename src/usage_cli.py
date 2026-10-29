"""يسجّل لقطة الحصة من أمر `claude -p "/usage"` بلا أي استدعاء للنموذج (لا توكنات ولا جلسة محفوظة).

يقرأ نسب الجلسة (5 ساعات) والأسبوع (كل النماذج) والأسبوع (Fable) مع أوقات التصفير، وعدّاد الطلبات والجلسات لـ24 ساعة و7 أيام،
ويحفظها في plan_snapshots (المصدر cli_usage) وcli_usage_counts. لا يحفظ نص التوصيات ولا أسماء الأدوات.
التشغيل: python src\\usage_cli.py [--db ...] ؛ مصمَّم للمهمة المجدولة MaestroUsageSnapshot كل ساعة.
رمز الخروج: 0 سُجّلت لقطة، 1 فشل التشغيل أو التحليل، 2 بيانات قديمة (آخر معلوم) فلم تُسجَّل.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_db  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CWD = os.path.join(ROOT, "data", "usage_cli_cwd")
LOG = os.path.join(ROOT, "data", "usage_cli.log")
TIMEOUT_SEC = 150
FIXED_ZONES = {"Asia/Qatar": 3}  # احتياط إن غابت قاعدة المناطق الزمنية في ويندوز
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
WINDOWS = (("five", r"Current session"), ("seven", r"Current week \(all models\)"), ("fable", r"Current week \(Fable\)"))
RESET = r"(?: · resets (?P<mon>[A-Z][a-z]{2}) (?P<day>\d{1,2}), (?P<h>\d{1,2})(?::(?P<m>\d\d))?(?P<ap>am|pm) \((?P<tz>[^)]+)\))?"
COUNT_RE = re.compile(r"^Last (24h|7d) · (\d+) requests · (\d+) sessions", re.M)
STALE_MARKERS = ("Showing last-known usage", "rate limited")


def _zone(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 — غياب tzdata أو اسم غير معروف
        return timezone(timedelta(hours=FIXED_ZONES[name])) if name in FIXED_ZONES else None


def _reset_iso(g, now):
    """«Oct 29, 10:49pm (Asia/Qatar)» ← ISO بتوقيت UTC؛ السنة من الوقت الحالي (التصفير دائمًا في المستقبل)."""
    zone = _zone(g["tz"])
    if zone is None or g["mon"] not in MONTHS:
        return None
    hour = int(g["h"]) % 12 + (12 if g["ap"] == "pm" else 0)
    local = datetime(now.year, MONTHS[g["mon"]], int(g["day"]), hour, int(g["m"] or 0), tzinfo=zone)
    if local < now - timedelta(days=1):
        local = local.replace(year=now.year + 1)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(text, now=None):
    """{five, five_resets, seven, seven_resets, fable, fable_resets, counts: [(نافذة, طلبات, جلسات)]} أو None إن لم يظهر شيء."""
    now = now or datetime.now(timezone.utc)
    out = {}
    for key, label in WINDOWS:
        m = re.search(r"^%s: (?P<pct>\d+(?:\.\d+)?)%% used%s" % (label, RESET), text, re.M)
        if m:
            out[key] = float(m.group("pct"))
            out[key + "_resets"] = _reset_iso(m.groupdict(), now) if m.group("mon") else None
    out["counts"] = [(w, int(r), int(s)) for w, r, s in COUNT_RE.findall(text)]
    return out if "five" in out or "seven" in out else None


def is_stale(text):
    return any(s in text for s in STALE_MARKERS)


def record(con, p, ts=None):
    ts = ts or usage_db.now_iso()
    # الفهرس الفريد لا يمنع التكرار مع session_key فارغ (NULL مختلف عن NULL)، فالتفريد بالفحص الصريح
    cur = con.execute(
        "INSERT INTO plan_snapshots(ts, session_key, five_hour_pct, five_hour_resets_at, seven_day_pct, "
        "seven_day_resets_at, source, plan, fable_pct, fable_resets_at) "
        "SELECT ?,NULL,?,?,?,?, 'cli_usage', NULL, ?, ? "
        "WHERE NOT EXISTS (SELECT 1 FROM plan_snapshots WHERE ts=? AND source='cli_usage')",
        (ts, p.get("five"), p.get("five_resets"), p.get("seven"), p.get("seven_resets"), p.get("fable"), p.get("fable_resets"), ts))
    for window, requests, sessions in p["counts"]:
        con.execute("INSERT OR IGNORE INTO cli_usage_counts(ts, window, requests, sessions) VALUES (?,?,?,?)",
                    (ts, window, requests, sessions))
    con.commit()
    return cur.rowcount


def run_claude():
    exe = shutil.which("claude") or os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe")
    os.makedirs(CWD, exist_ok=True)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run([exe, "--safe-mode", "--no-session-persistence", "-p", "/usage"], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT_SEC, cwd=CWD, creationflags=flags)
    return r.stdout


def _log(line):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (usage_db.now_iso(), line))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db")
    ap.add_argument("--text-file", help="تحليل نص محفوظ بدل تشغيل claude (للاختبار اليدوي)")
    a = ap.parse_args(argv)
    try:
        if a.text_file:
            with open(a.text_file, encoding="utf-8") as f:
                text = f.read()
        else:
            text = run_claude()
    except (OSError, subprocess.SubprocessError) as e:
        _log("fail run %s" % type(e).__name__)
        print("fail")
        return 1
    if is_stale(text):
        _log("stale")
        print("stale")
        return 2
    p = parse(text)
    if p is None:
        _log("fail parse")
        print("fail")
        return 1
    n = record(usage_db.connect(a.db), p)
    line = "five=%s seven=%s fable=%s %s" % (p.get("five"), p.get("seven"), p.get("fable"), "recorded" if n else "duplicate")
    _log(line)
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
