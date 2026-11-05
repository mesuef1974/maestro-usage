"""يولّد docs/metrics.md من سجلّ المقاييس (src/metrics.py) وقسم المصادر والآليات أدناه؛ الاختبار يتحقق أن الملف مطابق للمولَّد.
التشغيل: python scripts/gen_metrics_doc.py  (يكتب الملف) · --check (يعيد 1 إن اختلف)."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import metrics  # noqa: E402

OUT = os.path.join(ROOT, "docs", "metrics.md")

SOURCES = """## مصادر البيانات والآليات

| المصدر | الآلية | الجدول/الملف | التكرار | ما يُحفظ |
| --- | --- | --- | --- | --- |
| نسخ Claude Code النصية (`~/.claude/projects/**/*.jsonl`) | `usage_ingest.py`: يقرأ السطور الجديدة فقط بموضع الملف، ويأخذ من كل ردّ مساعد أرقام usage ومعرّفه | `usage_turns` | كل دقيقة | أرقام ومعرّفات فقط، بلا نص |
| سطر الحالة (statusLine) | `statusline_collector.py` يكتب لقطة إلى spool، و`statusline_loader.py` يحمّلها | `statusline_samples`، `plan_snapshots` | مع كل ردّ | نسب الحصة وحجم السياق |
| أمر `/usage` | `usage_cli.py` كل 5 دقائق (وكل دقيقة عند تغيّر النسب) و`record_usage.py` | `plan_snapshots`، `cli_usage_counts` | 5 دقائق | نسب النوافذ وأزمنة التصفير |
| الجلسات السحابية | `import_external.py` من `data/external/*.json` (أرقام مصدَّرة يدويًّا) | `usage_turns` (source_path يبدأ بـ`external:`) | عند وجود ملف جديد | أرقام الجلسة |
| مجلد `~/.claude` | `storage_scan.py` | `storage_scans`، `storage_dirs` | كل ساعة | أحجام وأعمار الملفات |
| المهارات | `skill_usage.py` يعدّ استدعاءات Skill في السجلات المحلية | `data/skill_usage.json` | كل دورة | عدد الاستدعاءات لكل مهارة |
| دفتر المشغّل | `runner_page.snapshot` يقرأ دفتر `delivery_manager_work` | `/runner.json` (حيّ) | كل طلب | حالة المشغّل والمهمة الجارية |
| نسب المنتجات | إدخال يدوي من بطاقة الحصة (`POST /share`) | `data/product_share.json` | أسبوعيًّا بيد المالك | حصة Claude Code وCowork والمحادثات |
| صحة الدورة | `run_cycle.write_health` بعد كل دورة | `data/health.json` → `/health.json` | كل دقيقة | نجاح آخر دورة وأخطاء الإدخال |

التجميعات (`usage_rollups`) تُعاد كتابتها عند أي بيانات جديدة في الدورة، والصفحة تُبنى حين تتغيّر البيانات أو الكود، وكل بناء يسجّل زمن مراحله في `data/cycle.log`.

**نطاق الأرقام:** نسبة الحصة من لقطات `/usage` تشمل كل منتجات الحساب، أما التوكنات فمن Claude Code على هذا الجهاز فقط؛ ولذلك تُصحَّح «كلفة 1%» بحصة Claude Code المُدخلة يدويًّا.
"""


def strip_html(s):
    s = re.sub(r'<span data-fill="([^"]+)"></span>', r"«\1»", s)
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("‎", "").strip()


def render():
    rows = ["| المقياس | الوحدة | المصدر | النافذة | التعريف |", "| --- | --- | --- | --- | --- |"]
    for m in metrics.METRICS:
        rows.append("| %s | %s | %s | %s | %s |" % (m["name"], m["unit"], m["source"], m["window"], strip_html(m["definition"]).replace("|", "\\|")))
    return ("# مقاييس ميزان: التعريف والمصدر\n\n"
            "مولَّد من `src/metrics.py` بأمر `python scripts/gen_metrics_doc.py`؛ لا يُحرَّر يدويًّا. "
            "الكلمات بين «» أرقام تملؤها الصفحة من الحمولة.\n\n"
            "## المقاييس\n\n" + "\n".join(rows) + "\n\n" + SOURCES)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    text = render()
    if "--check" in argv:
        try:
            cur = open(OUT, encoding="utf-8").read()
        except OSError:
            cur = ""
        return 0 if cur == text else 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
