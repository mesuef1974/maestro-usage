"""صفحة «ملخص الاستهلاك»: آخر جلسة ونماذجها، والأسبوعي والشهري، من usage_rollups. أرقام فقط وكلها من القاعدة."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rollups  # noqa: E402
import ui  # noqa: E402


def payload(con):
    return dict(summary=rollups.payload(con))


