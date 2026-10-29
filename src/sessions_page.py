"""صفحة «الأدوار والجلسات» الذاتية: استهلاك كل دور (رقم) وضغطه ومساره اليومي وكلفة إيقاظه ومن بدأ أدواره. أرقام ومعرّفات فقط.

جدول الحقائق C = جلسة × يوم × نموذج × أصل الدور. الأدوار تُجمَّع من الجلسات بالرقم، والمرشِّحات تُحسب في المتصفح.
تعريفات تُحسب هنا من أدوار الخيط الرئيس (بلا الوكلاء الفرعيين، لأن سياقاتهم مستقلّة وصغيرة):
- الإيقاظ: ردّ يأتي بعد فجوة تزيد على ساعة عن الردّ السابق في الجلسة نفسها (الردّ الأول في الجلسة ليس إيقاظًا).
- هبوط السياق (تقدير للضغط/المسح): ردّ سياقه أقل من نصف سياق الردّ السابق وكان السابق ≥ 100 ألف.
  لا يسجّل Claude Code الضغط في السجلات التي نقرؤها، فالرقم استدلال لا عدّ.
"""
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402  (مجموعات النماذج والعتبة نفسها)
import ui  # noqa: E402

WAKE_GAP_SEC = 3600
DROP_RATIO = 0.5
DROP_MIN_PREV = 100_000
PROJECT_RE = re.compile(r"^0[1-8]\d\d$")  # أدوار المشروع 01xx..08xx
UNNUMBERED = "غير مرقّمة"
SUB = "sub"  # أصل صوري لردود الوكلاء الفرعيين (turn_origin فيها NULL)


def folder_label(cwd):
    """اسم مجلد العمل فقط؛ شجرة عمل git تُعرض «المستودع › الشجرة» كي لا يضيع اسم المشروع."""
    p = (cwd or "").replace("\\", "/").rstrip("/")
    if not p:
        return ""
    parts = p.split("/")
    if ".claude" in parts and "worktrees" in parts:
        i = parts.index(".claude")
        if i > 0:
            return "%s › %s" % (parts[i - 1], parts[-1])
    return parts[-1]


def _epoch(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def payload(con):
    meta = {k: (n or "", cwd or "") for k, n, cwd in con.execute("SELECT session_key, number, cwd FROM sessions")}
    roles, role_of = [], {}

    def role_idx(number):
        key = number if number else UNNUMBERED
        if key not in role_of:
            role_of[key] = len(roles)
            roles.append(dict(n=key, p=bool(PROJECT_RE.match(key))))
        return role_of[key]

    sess, sess_of = [], {}
    facts = {}
    prev = {}  # session_key -> (epoch, ctx) لآخر ردّ رئيس
    cur = con.execute(
        "SELECT session_key, ts, model, input_tokens, cache_creation_tokens, cache_read_tokens, output_tokens, is_sidechain, turn_origin "
        "FROM usage_turns ORDER BY session_key, ts, message_id")
    for key, ts, model, i, cc, cr, u, side, org in cur:
        if key not in sess_of:
            number, cwd = meta.get(key, ("", ""))
            sess_of[key] = len(sess)
            sess.append(dict(k=key[:8], n=number, f=folder_label(cwd), r=role_idx(number)))
        ctx = i + cc + cr
        g = SUB if side else dashboard._origin(org)
        wk = wc = dr = 0
        if not side:
            epoch = _epoch(ts)
            p = prev.get(key)
            if p:
                if epoch - p[0] > WAKE_GAP_SEC:
                    wk, wc = 1, cc
                if p[1] >= DROP_MIN_PREV and ctx < DROP_RATIO * p[1]:
                    dr = 1
            prev[key] = (epoch, ctx)
        k = (sess_of[key], ts[:10], dashboard._group(model), g)
        r = facts.setdefault(k, [0] * 10)  # t,i,cc,cr,u,v,mx,dr,wk,wc
        v = 0 if side else int(ctx > dashboard.THRESHOLD)
        for j, x in enumerate((1, i, cc, cr, u, v)):
            r[j] += x
        if not side and ctx > r[6]:
            r[6] = ctx
        r[7] += dr
        r[8] += wk
        r[9] += wc
    rows = [dict(s=k[0], d=k[1], m=k[2], g=k[3], t=r[0], i=r[1], cc=r[2], cr=r[3], u=r[4], v=r[5], mx=r[6], dr=r[7], wk=r[8], wc=r[9])
            for k, r in sorted(facts.items())]
    first, last = con.execute("SELECT MIN(substr(ts,1,10)), MAX(substr(ts,1,10)) FROM usage_turns").fetchone()
    return dict(models=[n for _m, n in dashboard.MODEL_GROUPS] + [dashboard.OTHER_NAME], threshold=dashboard.THRESHOLD,
                wake_gap=WAKE_GAP_SEC, drop_ratio=DROP_RATIO, drop_min=DROP_MIN_PREV,
                first_day=first, last_day=last, roles=roles, sessions=sess, c=rows)


def render(data, stamp):
    return ui.render("sessions.html", data, {"__STAMP__": stamp})


def write(path, data, stamp):
    ui.write(path, render(data, stamp))
