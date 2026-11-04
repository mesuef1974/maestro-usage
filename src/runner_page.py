"""صفحة «المشغّل الحيّ» (D-519م): رحلة البطاقة في المشغّل لحظةً بلحظة، من الطابور إلى الإنتاج بلا جلسات.

القالب ساكن كبقيّة الصفحات؛ والبيانات الحيّة من GET /runner.json في serve.py كلّ ثانيتين، وهو يقرأ دفتر
مجلّد المدير بأداة delivery_manager_work/tools/runner_live.py (تقرأ فقط ولا تكتب، بصفر توكنز). مسار الأداة
من متغيّر البيئة RUNNER_LIVE، وإلّا فالافتراضيّ تحت مجلّد المستخدم.
"""
import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui  # noqa: E402

DEFAULT_SOURCE = Path.home() / "delivery_manager_work" / "tools" / "runner_live.py"
_MOD = None


def source_path():
    return Path(os.environ.get("RUNNER_LIVE") or DEFAULT_SOURCE)


def snapshot():
    """لقطة المشغّل الآن؛ الأداة تُحمَّل مرّة واحدة وتقرأ الدفتر تزايديًّا من آخر موضع."""
    global _MOD
    if _MOD is None:
        path = source_path()
        spec = importlib.util.spec_from_file_location("runner_live", path)
        if spec is None or spec.loader is None or not path.is_file():
            raise OSError("أداة المشغّل الحيّ غير موجودة: %s" % path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MOD = mod
    return _MOD.LEDGER.snapshot()


def payload():
    return dict(runner=dict(api="runner.json", source=str(source_path())))


