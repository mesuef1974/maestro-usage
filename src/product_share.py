"""نسبة استهلاك الحساب حسب المنتج (Claude Code وCowork والمحادثات) كما تعرضها صفحة الاستخدام في حساب المالك.

لا مصدر آليًّا لهذه النسب؛ يكتبها المالك يدويًّا من بطاقة الحصة في الصفحة فتُحفظ في data/product_share.json.
تُستعمل لتصحيح «كلفة 1%»: التوكنات المقاسة هي توكنات Claude Code وحدها، فالكلفة الحقيقية ≈ المقاسة ÷ حصة Claude Code.
"""
import json
import os
from datetime import datetime, timezone

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
PATH = os.path.join(DATA, "product_share.json")
KEYS = ("claude_code", "cowork", "chats", "other")
STALE_DAYS = 8  # النسبة أسبوعية؛ أقدم من أسبوع تُعرض بتحذير


def load(path=None):
    path = path or PATH
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not all(isinstance(d.get(k), (int, float)) for k in KEYS):
        return None
    return d


def validate(params):
    """يقبل {claude_code, cowork, chats, other} بالنسبة المئوية ويعيدها مرتّبة، أو يرفع ValueError."""
    if not isinstance(params, dict):
        raise ValueError("جسم غير صالح")
    out = {}
    for k in KEYS:
        v = params.get(k, 0)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 or v > 100:
            raise ValueError("نسبة %s يجب أن تكون بين 0 و100" % k)
        out[k] = round(float(v), 1)
    total = sum(out.values())
    if not 95 <= total <= 105:
        raise ValueError("مجموع النسب %.0f%% وليس نحو 100%%" % total)
    return out


def save(params, path=None, now=None):
    path = path or PATH
    out = validate(params)
    out["saved_at"] = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, path)
    return out


def payload(path=None, now=None):
    """للصفحة: النسب وحصة Claude Code كنسبة (0–1) ومعامل التصحيح وعمر الإدخال."""
    d = load(path or PATH)
    if not d:
        return dict(share=None, factor=None, age_days=None, stale=True)
    cc = d["claude_code"] / 100.0
    now = now or datetime.now(timezone.utc)
    try:
        age = (now - datetime.strptime(d["saved_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).days
    except (KeyError, ValueError):
        age = None
    return dict(share={k: d[k] for k in KEYS}, factor=(1 / cc) if cc > 0 else None, age_days=age, saved_at=d.get("saved_at"),
                stale=age is None or age > STALE_DAYS)
