"""تقارير الاستهلاك: CSV لكل تقرير وصفحة HTML ساكنة (RTL، عربية، بلا مكتبات). كل رقم محسوب من القاعدة.

المنجز الآن: التقارير 1 و2 و3. (4 و5 في دفعة لاحقة.)
"""
import csv
import html
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_db  # noqa: E402

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
MIN_TURNS_SUMMARY = 50  # جلسات أقل من هذا لا تدخل جدول الصفحة (تصدّرته جلسات من ردّ واحد)
CTX_THRESHOLD = 300_000  # توكن؛ سياق الردّ = input + cache_creation + cache_read (SPEC §3-2)


def session_label(number, key, cwd):
    folder = os.path.basename((cwd or "").replace("\\", "/").rstrip("/")) if cwd else ""
    return ("%s · %s" % (number, key[:8])) if number else ("%s%s" % (key[:8], (" · " + folder) if folder else ""))


def report1(con):
    """توكنز كل جلسة موزّعة على النموذج واليوم، والترتيب بنسبة قراءة الذاكرة إلى المخرجات."""
    rows = con.execute("""
        SELECT d.session_key, COALESCE(s.number, ''), COALESCE(s.cwd, ''), d.day, d.model, d.turns, d.input_tokens,
               d.cache_creation_tokens, d.cache_read_tokens, d.output_tokens,
               r.read_per_output
        FROM v_session_daily d
        JOIN sessions s ON s.session_key = d.session_key
        JOIN v_cache_ratio r ON r.session_key = d.session_key
        ORDER BY (r.read_per_output IS NULL), r.read_per_output DESC, d.session_key, d.day, d.model""").fetchall()
    header = ["session_key", "number", "cwd", "day", "model", "turns", "input_tokens", "cache_creation_tokens",
              "cache_read_tokens", "output_tokens", "session_read_per_output"]
    summary = con.execute("""
        SELECT r.session_key, COALESCE(s.number, ''), COALESCE(s.cwd, ''), r.turns, r.cache_read_tokens, r.output_tokens,
               r.read_per_output, s.first_seen, s.last_seen
        FROM v_cache_ratio r JOIN sessions s ON s.session_key = r.session_key
        WHERE r.turns >= ?
        ORDER BY r.read_per_output DESC LIMIT 25""", (MIN_TURNS_SUMMARY,)).fetchall()
    return header, rows, summary


def report2(con):
    """أسوأ عشر جلسات سياقًا: عدد الردود التي سياقها فوق 300 ألف، مع أكبر سياق ومتوسطه."""
    q = """
        SELECT t.session_key, COALESCE(s.number, ''), COALESCE(s.cwd, ''),
               COUNT(*) AS turns_all,
               SUM(CASE WHEN c > ? THEN 1 ELSE 0 END) AS turns_over,
               MAX(c) AS max_ctx,
               AVG(CASE WHEN c > ? THEN c END) AS avg_over,
               SUM(CASE WHEN c > ? THEN cr ELSE 0 END) AS cache_read_over
        FROM (SELECT session_key, input_tokens + cache_creation_tokens + cache_read_tokens AS c,
                     cache_read_tokens AS cr FROM usage_turns) t
        JOIN sessions s ON s.session_key = t.session_key
        GROUP BY t.session_key
        HAVING turns_over > 0
        ORDER BY turns_over DESC, max_ctx DESC LIMIT 10"""
    rows = con.execute(q, (CTX_THRESHOLD, CTX_THRESHOLD, CTX_THRESHOLD)).fetchall()
    header = ["session_key", "number", "cwd", "turns_all", "turns_over_300k", "max_context", "avg_context_over_300k",
              "cache_read_in_over_300k_turns"]
    totals = con.execute("""SELECT COUNT(*), SUM(CASE WHEN c > ? THEN 1 ELSE 0 END),
                                   SUM(CASE WHEN c > ? THEN cr ELSE 0 END), SUM(cr)
                            FROM (SELECT input_tokens + cache_creation_tokens + cache_read_tokens AS c,
                                         cache_read_tokens AS cr FROM usage_turns)""", (CTX_THRESHOLD, CTX_THRESHOLD)).fetchone()
    return header, rows, totals


WINDOW_DAYS = 7


def _window(con, d0, d1):
    r = con.execute("""
        SELECT COUNT(*), COUNT(DISTINCT substr(ts,1,10)), COUNT(DISTINCT session_key),
               COALESCE(SUM(input_tokens + cache_creation_tokens + cache_read_tokens + output_tokens), 0),
               COALESCE(SUM(cache_read_tokens), 0), COALESCE(SUM(output_tokens), 0),
               COALESCE(AVG(input_tokens + cache_creation_tokens + cache_read_tokens), 0)
        FROM usage_turns WHERE substr(ts,1,10) >= ? AND substr(ts,1,10) < ?""", (d0, d1)).fetchone()
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


# ---------------- الإخراج ----------------

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


CSS = """
:root{--bg:#fafaf7;--fg:#1a1a1a;--mut:#666;--bd:#d8d8d0;--hd:#eeeee6}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--fg:#e8e8e8;--mut:#9a9a9a;--bd:#3a3a3a;--hd:#242424}}
body{background:var(--bg);color:var(--fg);font:15px/1.7 "Segoe UI",Tahoma,sans-serif;margin:0 auto;max-inline-size:1100px;padding:1rem 1rem 4rem}
h1{font-size:1.5rem}h2{margin-block-start:2.5rem;font-size:1.2rem;border-block-end:1px solid var(--bd)}
table{border-collapse:collapse;inline-size:100%;margin-block:.5rem;font-size:.85rem}
th,td{border:1px solid var(--bd);padding:.3rem .5rem;text-align:start}th{background:var(--hd)}
td{font-variant-numeric:tabular-nums}.src,.note{color:var(--mut);font-size:.8rem}.warn{color:#b45309}
.wrap{overflow-x:auto}
"""


def build(con, out_dir=REPORTS_DIR):
    os.makedirs(out_dir, exist_ok=True)
    stamp = con.execute("SELECT MAX(updated_at) FROM ingest_state").fetchone()[0] or "—"
    parts = []

    h1, rows1, summ1 = report1(con)
    write_csv(os.path.join(out_dir, "report1_session_model_day.csv"), h1, rows1)
    tot = con.execute("SELECT COUNT(*), SUM(cache_read_tokens), SUM(output_tokens) FROM usage_turns").fetchone()
    parts.append("<h2>1. توكنز كل جلسة موزّعة على النموذج واليوم</h2>")
    parts.append('<p>الترتيب بنسبة قراءة الذاكرة المؤقتة إلى المخرجات. الجدول أدناه أعلى 25 جلسة ذات 50 ردًّا فأكثر (وإلا تصدّرته جلسات من ردّ واحد)؛ التفصيل كاملًا (جلسة × يوم × نموذج، %s صفًّا) في report1_session_model_day.csv.</p>' % fmt(len(rows1)))
    parts.append('<div class="wrap">%s</div>' % table(
        ["الجلسة", "ردود", "قراءة ذاكرة", "مخرجات", "قراءة ÷ مخرجات", "أول ظهور", "آخر ظهور"],
        [(session_label(n, k, c), fmt(t), fmt(cr), fmt(o), fmt(rp), (fs or "")[:10], (ls or "")[:10])
         for k, n, c, t, cr, o, rp, fs, ls in summ1]))
    parts.append('<p class="note">ملاحظة: الرقم الرباعي في اسم الجلسة مأخوذ من بادئة عنوانها، وقد يطابق عنوانًا ليس من جلسات الفلو (مثل سنة). الإجمالي: %s ردًّا، قراءة ذاكرة %s، مخرجات %s، النسبة العامة %s.</p>' % (
        fmt(tot[0]), fmt(tot[1]), fmt(tot[2]), fmt(tot[1] / tot[2] if tot[2] else None)))
    parts.append(source("جدول usage_turns (عروض v_session_daily وv_cache_ratio)", stamp))

    h2, rows2, t2 = report2(con)
    write_csv(os.path.join(out_dir, "report2_worst_context.csv"), h2, rows2)
    parts.append("<h2>2. أسوأ عشر جلسات سياقًا</h2>")
    parts.append("<p>سياق الردّ = المدخلات + كتابة الذاكرة + قراءة الذاكرة. الجلسات مرتّبة بعدد الردود التي سياقها فوق 300 ألف توكن.</p>")
    parts.append('<div class="wrap">%s</div>' % table(
        ["الجلسة", "كل الردود", "ردود فوق 300 ألف", "أكبر سياق", "متوسط السياق فوقها", "قراءة ذاكرة فيها"],
        [(session_label(n, k, c), fmt(ta), fmt(to), fmt(mx), fmt(av), fmt(cro)) for k, n, c, ta, to, mx, av, cro in rows2]))
    share = (t2[2] / t2[3]) if t2[3] else None
    parts.append('<p class="note">على مستوى كل القاعدة: %s من %s ردًّا (%s%%) سياقه فوق 300 ألف، وتحمل %s%% من قراءة الذاكرة.</p>' % (
        fmt(t2[1]), fmt(t2[0]), fmt(100 * t2[1] / t2[0] if t2[0] else None, 1), fmt(100 * share if share is not None else None, 1)))
    parts.append(source("جدول usage_turns", stamp))

    r3 = report3(con)
    rows3 = []
    parts.append("<h2>3. سبعة أيام قبل كل تغيير إعداد وسبعة بعده</h2>")
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

    page = ('<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>تقارير استهلاك Claude Code</title><style>%s</style></head><body><h1>تقارير استهلاك Claude Code</h1>'
            '<p class="note">وُلّدت محليًّا في %s من القاعدة flow_usage.sqlite3. أرقام فقط؛ لا نصوص محادثات. المقياس توكن لا دولار (الخطة اشتراك ثابت).</p>%s</body></html>'
            % (CSS, html.escape(datetime.now().strftime("%Y-%m-%d %H:%M")), "".join(parts)))
    path = os.path.join(out_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path


if __name__ == "__main__":
    print(build(usage_db.connect()))
