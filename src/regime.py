"""نظام نافذة السياق (autoCompactWindow) الذي قرأته العملية عند بدئها، لكل ردّ.

الإعداد يُقرأ عند بدء العملية لا عند كل ردّ. بدء العملية معروف فقط للجلسات الملتقطة في agent_starts (من أول التقاط)؛
لغيرها يُستدلّ بما يمكن الجزم به:
- ردّ قبل أول تغيير: العملية بدأت قبله → افتراضي.
- ردّ بعد أول تغيير وقبل الأخير، والجلسة نفسها أُنشئت (أول ردّ) بعد أول تغيير → النظام الأول؛ وإلا غير محدد.
- ردّ بعد آخر تغيير ببدء غير معروف → غير محدد (قد تكون العملية بدأت قبله).
زمن تغيير بصيغة يوم فقط يُحسب من بداية اليوم، فجلسة بدأت صباح ذلك اليوم قد تُصنَّف 250 ألفًا وهي افتراضية.
"""
import bisect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_db  # noqa: E402

NAMES = ["افتراضي", "250 ألفًا", "مليون", "غير محدد"]
DEFAULT, W250, W1M, UNKNOWN = range(4)
_CODE = {"250000": W250, "1000000": W1M}


def changes():
    """[(ts, code)] مرتبة من بذور config_changes لمفتاح autoCompactWindow."""
    out = []
    for ts, key, _old, new, _note in usage_db.CONFIG_SEEDS:
        if key == "autoCompactWindow" and new in _CODE:
            out.append((ts if "T" in ts else ts + "T00:00:00Z", _CODE[new]))
    return sorted(out)


def by_start(start, ch=None):
    """نظام عملية بدأت عند start (ISO)."""
    ch = ch or changes()
    i = bisect.bisect_right([t for t, _c in ch], start)
    return ch[i - 1][1] if i else DEFAULT


def classify(ts, first_ts, starts, ch=None):
    """نظام ردّ بزمن ts في جلسة أول ردّ لها first_ts وأزمنة بدء عملياتها المعروفة starts (مرتبة)."""
    ch = ch or changes()
    i = bisect.bisect_right(starts, ts)
    if i:
        return by_start(starts[i - 1], ch)
    if not ch or ts < ch[0][0]:
        return DEFAULT
    if ts < ch[-1][0] and first_ts >= ch[0][0]:
        return by_start(ts, ch)
    return UNKNOWN
