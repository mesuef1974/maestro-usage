"""تقديم طلبٍ من الطرفية عبر دالة الاستمارة نفسها: الأنواع والمعايير والأحجام تُتحقَّق وقت الكتابة لا عند إعادة المحاولة.
الاستعمال: python src/submit_cli.py طلب.json   (أو JSON من الإدخال القياسي بلا وسيط). يطبع اسم الملف أو سببَ الرفض ويُخرج بـ2."""
import json
import sys

import request_page


def run(raw):
    try:
        out = request_page.submit(json.loads(raw))
    except request_page.ValidationError as exc:
        return 2, "رُفض (%s): %s" % (getattr(exc, "field", ""), exc)
    except json.JSONDecodeError as exc:
        return 2, "JSON غير صالح: %s" % exc
    return 0, out["file"]


def main(argv):
    raw = open(argv[1], encoding="utf-8").read() if len(argv) > 1 else sys.stdin.read()
    code, msg = run(raw)
    print(msg)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
