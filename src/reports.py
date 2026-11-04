"""تقارير الاستهلاك: CSV لكل تقرير وصفحة HTML ساكنة (RTL، عربية، بلا مكتبات). كل رقم محسوب من القاعدة.

التقارير 1-5. التقرير 4 فارغ حتى تصل عيّنات statusLine؛ التقرير 5 مبني على turn_origin (فئة يسجّلها Claude Code نفسه).
"""
import csv
import html
import os
import statistics
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402
import hourly_page  # noqa: E402
import pages  # noqa: E402
import sessions_page  # noqa: E402
import skills_page  # noqa: E402
import storage_page  # noqa: E402
import flow_page  # noqa: E402
import request_page  # noqa: E402
import runner_page  # noqa: E402
import summary_page  # noqa: E402
import ui  # noqa: E402
import usage_db  # noqa: E402

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
NOT_APPLIED_MARK = "لم تُطبَّق"  # علامة في note تُسقِط التغيير من مقارنة قبل/بعد (التقرير 3)
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


def report4(con):
    """نسبة الحصة الأسبوعية (وخمس الساعات) حسب اليوم من plan_snapshots؛ أعلى قيمة في اليوم."""
    rows = con.execute("""
        SELECT substr(ts, 1, 10) AS day, source, COUNT(*), MAX(seven_day_pct), MAX(five_hour_pct)
        FROM plan_snapshots GROUP BY substr(ts, 1, 10), source ORDER BY day""").fetchall()
    return ["day", "source", "samples", "max_seven_day_pct", "max_five_hour_pct"], rows


def _ts(s):
    return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").timestamp()


def report5(con):
    """كلفة الدورة الدورية (turn_origin='scheduled') في جلسات 0101 مقابل كل الاستهلاك، وتوزيع الأصول.

    التمييز: الحقل turnOrigin يسجّله Claude Code على سطر المستخدم الذي بدأ الدور؛ والردود اللاحقة تأخذ آخر قيمة.
    الحدود: 'scheduled' تشمل كل ما جدولته الجلسة (الدورة كل 5 دقائق وغيرها) فلا يُفصل 5 دقائق عن غيرها بالحقل وحده؛
    ولذا يُعرض توزيع فواصل بدايات الدورات كدليل مستقل. الوكلاء الفرعيون بلا أصل (NULL).
    """
    origins = con.execute("""
        SELECT COALESCE(turn_origin, 'unknown'), COUNT(*), SUM(input_tokens), SUM(cache_creation_tokens),
               SUM(cache_read_tokens), SUM(output_tokens)
        FROM usage_turns GROUP BY 1 ORDER BY 5 DESC""").fetchall()
    total_cr = sum(r[4] for r in origins) or 1
    sched = con.execute("""
        SELECT s.session_key, t.ts, t.cache_read_tokens, t.cache_creation_tokens, t.output_tokens
        FROM usage_turns t JOIN sessions s ON s.session_key = t.session_key
        WHERE s.number = '0101' AND t.turn_origin = 'scheduled' ORDER BY s.session_key, t.ts""").fetchall()
    per_day = {}
    runs, prev, last, gaps = 0, {}, {}, []
    for key, ts, cr, cc, out in sched:
        d = per_day.setdefault(ts[:10], [0, 0, 0, 0])
        d[0] += 1
        d[1] += cr
        d[2] += cc
        d[3] += out
        t = _ts(ts)
        if key not in prev or t - prev[key] > 120:  # دور جديد (الردود المتلاحقة ضمن دور واحد)
            runs += 1
            if key in last and 0 < t - last[key] < 3600:
                gaps.append(t - last[key])
            last[key] = t
        prev[key] = t
    all_cr = con.execute("SELECT SUM(cache_read_tokens) FROM usage_turns").fetchone()[0] or 1
    s_cr = sum(r[2] for r in sched)
    gap_info = None
    if len(gaps) >= 8:
        q = statistics.quantiles(gaps, n=4)
        gap_info = dict(n=len(gaps), q1=q[0], median=q[1], q3=q[2], near5=sum(1 for g in gaps if 240 <= g <= 360) / len(gaps))
    return dict(origins=origins, total_cr=total_cr, per_day=sorted(per_day.items()), turns=len(sched), runs=runs,
                cache_read=s_cr, share_of_all=s_cr / all_cr, gap=gap_info,
                sessions=len({r[0] for r in sched}))


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

    r3_all = report3(con)
    r3 = [c for c in r3_all if NOT_APPLIED_MARK not in (c["note"] or "")]
    rows3 = []
    parts.append("<h2>3. سبعة أيام قبل كل تغيير إعداد وسبعة بعده</h2>")
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
    parts.append("<h2>4. نسبة الحصة الأسبوعية حسب اليوم</h2>")
    if rows4:
        parts.append('<div class="wrap">%s</div>' % table(["اليوم", "المصدر", "عيّنات", "أعلى نسبة أسبوعية %", "أعلى نسبة 5 ساعات %"],
                                                          [(d, sr, fmt(n), fmt(w, 1), fmt(f, 1)) for d, sr, n, w, f in rows4]))
    else:
        parts.append('<p class="warn">لا عيّنات حصة بعد: تصل من statusLine بعد أول ردّ في جلسة جديدة منذ التثبيت. السجلات القديمة لا تحمل نسبة الحصة، فلا تاريخ قبل التثبيت.</p>')
    parts.append(source("جدول plan_snapshots", stamp))

    r5 = report5(con)
    write_csv(os.path.join(out_dir, "report5_scheduled_cycle.csv"), ["day", "turns", "cache_read", "cache_creation", "output"],
              [[d] + v for d, v in r5["per_day"]])
    write_csv(os.path.join(out_dir, "report5_origins.csv"), ["turn_origin", "turns", "input", "cache_creation", "cache_read", "output"],
              [list(r) for r in r5["origins"]])
    parts.append("<h2>5. كلفة الدورة الدورية في جلسات 0101</h2>")
    parts.append("<p>أصل الدور (من حقل يسجّله Claude Code): من بدأ الدور؟ إنسان، أم جلسة أخرى (peer)، أم مجدول، أم إشعار مهمة، أم SDK.</p>")
    parts.append('<div class="wrap">%s</div>' % table(
        ["أصل الدور", "ردود", "كتابة ذاكرة", "قراءة ذاكرة", "حصة من قراءة الذاكرة %", "مخرجات"],
        [(o, fmt(n), fmt(cc), fmt(cr), fmt(100 * cr / r5["total_cr"], 1), fmt(out)) for o, n, _i, cc, cr, out in r5["origins"]]))
    parts.append('<p>الدورات المجدولة في جلسات 0101: <b>%s</b> ردًّا في %s دورة وفي %s جلسة، قراءة ذاكرتها %s أي <b>%s%%</b> من كل قراءة الذاكرة في القاعدة.</p>' % (
        fmt(r5["turns"]), fmt(r5["runs"]), fmt(r5["sessions"]), fmt(r5["cache_read"]), fmt(100 * r5["share_of_all"], 2)))
    if r5["gap"]:
        g = r5["gap"]
        parts.append('<p>فواصل بدايات الدورات (ثوانٍ، %s فاصلًا أقل من ساعة): الربع الأول %s، الوسيط %s، الربع الثالث %s؛ ونسبة الفواصل بين 240 و360 ثانية %s%%.</p>' % (
            fmt(g["n"]), fmt(g["q1"]), fmt(g["median"]), fmt(g["q3"]), fmt(100 * g["near5"], 0)))
    parts.append('<p class="note">درجة الثقة وحدودها: (أ) عالية في أن الردود موسومة «مجدولة» لأن Claude Code نفسه يسجّل الحقل، لا تخمين زمني. '
                 '(ب) متوسطة في أن كلها «الدورة كل 5 دقائق»: الحقل يشمل كل المجدول، والفواصل المقيسة لا تتركّز عند 5 دقائق (تتأخر الدورة حين تكون الجلسة مشغولة). '
                 '(ج) الكلفة تُقاس كحصة من قراءة الذاكرة لا كدولار. (د) الردود التالية في الدور نفسه تُنسب لأصله، فالدورة التي تستدعي أدوات تظهر بعدة ردود. '
                 '(هـ) الوكلاء الفرعيون بلا أصل فلا يدخلون هذا العدّ.</p>')
    parts.append(source("جدول usage_turns (العمود turn_origin) وربط الأرقام من sessions.number", stamp))

    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    ui.write_assets(out_dir)
    static = "".join(parts)
    payloads = {"dashboard.html": dashboard.payload(con, session_label, NOT_APPLIED_MARK, MIN_TURNS_SUMMARY),
                "sessions.html": sessions_page.payload(con), "hourly.html": hourly_page.payload(con), "skills.html": skills_page.payload(),
                "storage.html": storage_page.payload(con), "flow.html": flow_page.payload(), "runner.html": runner_page.payload(), "request.html": request_page.payload(), "summary.html": summary_page.payload(con)}
    for p in pages.PAGES:  # صفحة لكل سطر في السجلّ؛ القالب الواحد يخدم عدّة صفحات (الأقسام في pages.py)
        target, data = os.path.join(out_dir, p["file"]), payloads[p["template"]]
        if p["template"] == "dashboard.html":
            dashboard.write(target, data, static, gen, p["file"])
        elif p["template"] == "sessions.html":
            sessions_page.write(target, data, gen, p["file"])
        elif p["template"] == "hourly.html":
            hourly_page.write(target, data, gen, p["file"])
        elif p["template"] == "storage.html":
            storage_page.write(target, data, gen, p["file"])
        elif p["template"] == "flow.html":
            flow_page.write(target, data, gen, p["file"])
        elif p["template"] == "runner.html":
            runner_page.write(target, data, gen, p["file"])
        elif p["template"] == "summary.html":
            summary_page.write(target, data, gen, p["file"])
        elif p["template"] == "request.html":
            request_page.write(target, data, gen, p["file"])
        else:
            skills_page.write(target, data, gen, p["file"])
    return os.path.join(out_dir, "index.html")


if __name__ == "__main__":
    print(build(usage_db.connect()))
