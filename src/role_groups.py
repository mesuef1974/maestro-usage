"""اسم «الدور» لكل جلسة: الرقم إن وُجد، وإلا فئة مُستنتجة من مجلد العمل بدل سلّة واحدة مجهولة.

الجلسات بلا رقم (نحو ثلث قراءة الذاكرة كلها) ليست متجانسة: مراقب، ومستودع المشروع، ومدير التسليم، وأشجار عمل git.
تُفصَل هنا بمجلد العمل فقط (لا نصوص محادثات ولا عناوين)، وتبقى خارج «أدوار المشروع» 01xx–08xx.
"""
import re

PROJECT_RE = re.compile(r"^0[1-8]\d\d$")  # أدوار المشروع 01xx..08xx
PREFIX = "بلا رقم · "
# مجلد العمل (آخر مكوّن) -> اسم الفئة؛ ما عداها يُطوى في «أخرى»
FOLDERS = {"MonitorWidget": "مراقب MonitorWidget", "shschool_mvp": "مستودع shschool_mvp",
           "delivery_manager_work": "مدير التسليم delivery_manager_work"}
WORKTREE_REPOS = ("shschool_mvp", "delivery_manager_work", "MonitorWidget")
OTHER = PREFIX + "أخرى"


def unnumbered_group(cwd):
    p = (cwd or "").replace("\\", "/").rstrip("/")
    if not p:
        return OTHER
    parts = p.split("/")
    if ".claude" in parts and "worktrees" in parts:
        i = parts.index(".claude")
        repo = parts[i - 1] if i > 0 else ""
        return PREFIX + "أشجار عمل " + repo if repo in WORKTREE_REPOS else OTHER
    return PREFIX + FOLDERS[parts[-1]] if parts[-1] in FOLDERS else OTHER


def role_name(number, cwd):
    """الرقم كما سُجِّل (أدوار المشروع وأي رقم آخر مثل 8094) وإلا فئة المجلد."""
    return number if number else unnumbered_group(cwd)


def is_project(name):
    return bool(PROJECT_RE.match(name))
