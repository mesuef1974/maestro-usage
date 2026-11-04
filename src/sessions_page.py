"""ثوابت الإيقاظ وهبوط السياق واسم مجلد العمل، تستعملها hourly_page وstudy وstartup_cost.

كانت صفحة «الأدوار والجلسات» (حُذفت: الأتمتة الجديدة جلسة واحدة)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import role_groups  # noqa: E402

WAKE_GAP_SEC = 3600
DROP_RATIO = 0.5
DROP_MIN_PREV = 100_000
PROJECT_RE = role_groups.PROJECT_RE
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
