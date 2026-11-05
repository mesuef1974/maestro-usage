"""تقارير الاستهلاك: CSV لكل تقرير وصفحة HTML ساكنة (RTL، عربية، بلا مكتبات). كل رقم محسوب من القاعدة.

التقارير 1-5. التقرير 4 فارغ حتى تصل عيّنات statusLine؛ التقرير 5 مبني على turn_origin (فئة يسجّلها Claude Code نفسه).
"""
import csv
import html
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402
import hourly_page  # noqa: E402
import pages  # noqa: E402
import skills_page  # noqa: E402
import storage_page  # noqa: E402
import flow_page  # noqa: E402
import request_page  # noqa: E402
import runner_page  # noqa: E402
import summary_page  # noqa: E402
import onepage  # noqa: E402
import ui  # noqa: E402
import usage_db  # noqa: E402

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
NOT_APPLIED_MARK = "لم تُطبَّق"  # علامة في note تُسقِط التغيير من مقارنة قبل/بعد (التقرير 3)
MIN_TURNS_SUMMARY = 50  # جلسات أقل من هذا لا تدخل جدول الصفحة (تصدّرته جلسات من ردّ واحد)
CTX_THRESHOLD = 300_000  # توكن؛ سياق الردّ = input + cache_creation + cache_read (SPEC §3-2)








WINDOW_DAYS = 7


def _window(con, d0, d1):
    r = con.execute("""
        SELECT COUNT(*), COUNT(DISTINCT substr(ts,1,10)), COUNT(DISTINCT session_key),
               COALESCE(SUM(input_tokens + cache_creation_tokens + cache_read_tokens + output_tokens), 0),
               COALESCE(SUM(cache_read_tokens), 0), COALESCE(SUM(output_tokens), 0),
               COALESCE(AVG(input_tokens + cache_creation_tokens + cache_read_tokens), 0)
        FROM usage_turns WHERE ts >= ? AND ts < ?""", (d0, d1)).fetchone()  # مقارنة على ts نفسه ليعمل فهرس ix_turns_ts (التواريخ بادئة ISO)
    turns, active_days, sessions, total, cr, out, avg_ctx = r
    return dict(turns=turns, active_days=active_days, sessions=sessions, total=total, cache_read=cr, output=out,
                avg_context=avg_ctx, read_per_output=(cr / out if out else None))


def report3(con, today=None):
    """سبعة أيام قبل كل تغيير في config_changes وسبعة بعده بالمقاييس نفسها.

    قبل = [اليوم-7، اليوم)؛ بعد = [اليوم، اليوم+7) مقصوصة عند اليوم الحالي. التواريخ بالتوقيت العالمي.
    المقاييس تُقارن لكل يوم فعّال (أيام فيها ردود) كي لا يحجب نقصُ الأيام الأثر.
    """
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = []
    for cid, ts, key, old, new, note in con.execute("SELECT id, ts, key, old_value, new_value, note FROM config_changes ORDER BY ts, id"):
        d = date.fromisoformat(ts[:10])
        b0, b1 = (d - timedelta(days=WINDOW_DAYS)).isoformat(), d.isoformat()
        a0, a1 = d.isoformat(), min(d + timedelta(days=WINDOW_DAYS), date.fromisoformat(today) + timedelta(days=1)).isoformat()
        before, after = _window(con, b0, b1), _window(con, a0, a1)
        full_after_days = max(0, (date.fromisoformat(a1) - date.fromisoformat(a0)).days)
        out.append(dict(id=cid, ts=ts, key=key, old=old, new=new, note=note, before_range=(b0, b1), after_range=(a0, a1),
                        before=before, after=after, after_days_available=full_after_days))
    return out


def report4(con):
    """نسبة الحصة الأسبوعية (وخمس الساعات) حسب اليوم من plan_snapshots؛ أعلى قيمة في اليوم."""
    rows = con.execute("""
        SELECT substr(ts, 1, 10) AS day, source, COUNT(*), MAX(seven_day_pct), MAX(five_hour_pct)
        FROM plan_snapshots GROUP BY substr(ts, 1, 10), source ORDER BY day""").fetchall()
    return ["day", "source", "samples", "max_seven_day_pct", "max_five_hour_pct"], rows


def _ts(s):
    return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").timestamp()





def fmt(n, digits=0):
    if n is None:
        return "—"
    return ("{:,.%df}" % digits).format(n)


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def table(headers, rows):
    h = "".join("<th>%s</th>" % html.escape(x) for x in headers)
    b = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % html.escape(str(c)) for c in r) for r in rows)
    return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (h, b)


def source(text, stamp):
    return '<p class="src">المصدر: %s · آخر تحديث للقاعدة: %s (UTC)</p>' % (html.escape(text), html.escape(stamp))




TIMES = {}  # زمن مراحل آخر بناء بالثواني (يُكتب في سجل الدورة)


def build(con, out_dir=REPORTS_DIR):
    os.makedirs(out_dir, exist_ok=True)
    t_static = time.time()
    stamp = con.execute("SELECT MAX(updated_at) FROM ingest_state").fetchone()[0] or "—"
    parts = []

    r3_all = report3(con)
    r3 = [c for c in r3_all if NOT_APPLIED_MARK not in (c["note"] or "")]
    rows3 = []
    parts.append("<h2>1. سبعة أيام قبل كل تغيير إعداد وسبعة بعده</h2>")
    for c in r3_all:
        if NOT_APPLIED_MARK in (c["note"] or ""):
            parts.append('<p class="warn">أُسقط %s: %s ← %s (%s). التغيير لم يُطبَّق فعليًّا وفق get_usage، فلا تصحّ مقارنة قبل/بعد كأثر.</p>' % (
                html.escape(c["key"]), html.escape(str(c["new"])), html.escape(str(c["old"])), html.escape(c["ts"])))
    parts.append('<p class="note">قبل = 7 أيام قبل يوم التغيير؛ بعد = من يوم التغيير حتى 7 أيام أو حتى اليوم الحالي. المقارنة لكل يوم فعّال (فيه ردود). '
                 'اليوم بالتوقيت العالمي. تغييران في اليوم نفسه (9→45→25) لا يمكن فصل أثرهما.</p>')
    for c in r3:
        for label, w, rng in (("قبل", c["before"], c["before_range"]), ("بعد", c["after"], c["after_range"])):
            days = w["active_days"] or None
            rows3.append([c["ts"], c["key"], c["old"], c["new"], label, rng[0], rng[1], w["active_days"], w["sessions"], w["turns"],
                          w["total"], w["cache_read"], w["output"], w["avg_context"],
                          (w["total"] / days) if days else None, w["read_per_output"]])
    h3 = ["change_ts", "key", "old", "new", "window", "from", "to_exclusive", "active_days", "sessions", "turns", "total_tokens",
          "cache_read", "output", "avg_context_per_turn", "total_per_active_day", "read_per_output"]
    write_csv(os.path.join(out_dir, "report3_before_after.csv"), h3, rows3)
    for c in r3:
        parts.append("<h3>%s: %s ← %s <span class=\"note\">(%s)</span></h3>" % (
            html.escape(c["key"]), html.escape(str(c["new"])), html.escape(str(c["old"])), html.escape(c["ts"])))
        if c["after_range"][1] == (date.fromisoformat(datetime.now(timezone.utc).strftime("%Y-%m-%d")) + timedelta(days=1)).isoformat():
            parts.append('<p class="warn">نافذة «بعد» تنتهي باليوم الحالي وهو ناقص: لا تُقارن المجاميع، والأرقام لكل يوم فعّال أدلّ لكنها مبكرة جدًّا للحكم.</p>')
        if c["after"]["active_days"] == 0:
            parts.append('<p class="warn">لا أيام فعّالة بعد التغيير بعد؛ لا مقارنة ممكنة الآن (الأيام المتاحة بعده: %d).</p>' % c["after_days_available"])
        rws = []
        for label, w in (("قبل", c["before"]), ("بعد", c["after"])):
            d = w["active_days"] or None
            rws.append((label, fmt(w["active_days"]), fmt(w["sessions"]), fmt(w["turns"]), fmt(w["total"]),
                        fmt(w["total"] / d if d else None), fmt(w["avg_context"]), fmt(w["read_per_output"])))
        parts.append('<div class="wrap">%s</div>' % table(
            ["الفترة", "أيام فعّالة", "جلسات", "ردود", "إجمالي توكن", "توكن لكل يوم فعّال", "متوسط السياق للردّ", "قراءة ÷ مخرجات"], rws))
    parts.append(source("جداول usage_turns وconfig_changes", stamp))

    h4, rows4 = report4(con)
    write_csv(os.path.join(out_dir, "report4_weekly_quota_by_day.csv"), h4, rows4)
    parts.append("<h2>2. نسبة الحصة الأسبوعية حسب اليوم</h2>")
    if rows4:
        parts.append('<div class="wrap">%s</div>' % table(["اليوم", "المصدر", "عيّنات", "أعلى نسبة أسبوعية %", "أعلى نسبة 5 ساعات %"],
                                                          [(d, sr, fmt(n), fmt(w, 1), fmt(f, 1)) for d, sr, n, w, f in rows4]))
    else:
        parts.append('<p class="warn">لا عيّنات حصة بعد: تصل من statusLine بعد أول ردّ في جلسة جديدة منذ التثبيت. السجلات القديمة لا تحمل نسبة الحصة، فلا تاريخ قبل التثبيت.</p>')
    parts.append(source("جدول plan_snapshots", stamp))

    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    static_sec = round(time.time() - t_static, 1)
    ui.write_assets(out_dir)
    static = "".join(parts)
    makers = {"dashboard.html": lambda: dashboard.payload(con, NOT_APPLIED_MARK, MIN_TURNS_SUMMARY),
              "hourly.html": lambda: hourly_page.payload(con), "skills.html": skills_page.payload,
              "storage.html": lambda: storage_page.payload(con), "flow.html": flow_page.payload, "runner.html": runner_page.payload,
              "request.html": request_page.payload, "summary.html": lambda: summary_page.payload(con)}
    payloads = {}
    TIMES.clear()
    TIMES["static"] = static_sec
    for k, fn in makers.items():  # زمن كل حمولة يُسجَّل في TIMES ليظهر في سجل الدورة (أبطأ مرحلة تُعرف بالاسم)
        t0 = time.time()
        payloads[k] = fn()
        TIMES[k.split(".")[0]] = round(time.time() - t0, 1)
    parts = []
    for p in pages.PAGES:  # جزء لكل سطر في السجلّ؛ تجمعها onepage في index.html
        tokens = {"__STAMP__": gen, "__STATIC__": static}
        parts.append((p["file"], ui.render(p["file"], payloads[p["template"]], tokens), p["file"] in pages.SCRIPTLESS))
    t0 = time.time()
    ui.write(os.path.join(out_dir, "index.html"), onepage.build(parts, gen))
    TIMES["page"] = round(time.time() - t0, 1)
    for name in os.listdir(out_dir):  # صفحات المنصة القديمة (قبل الصفحة الواحدة) تُزال كي لا تُقدَّم قديمة
        if name.endswith(".html") and name != "index.html":
            try:
                os.remove(os.path.join(out_dir, name))
            except OSError:
                pass
    return os.path.join(out_dir, "index.html")


if __name__ == "__main__":
    print(build(usage_db.connect()))
