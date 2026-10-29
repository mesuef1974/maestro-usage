"""أجزاء مشتركة بين صفحات المنصة الذاتية: CSS ودوال JS للرسم، وتهريب JSON، والكتابة الذرّية."""
import json
import os
from pathlib import Path

SRC = Path(__file__).resolve().parent


def assets():
    return (SRC / "ui_common.css").read_text(encoding="utf-8"), (SRC / "ui_common.js").read_text(encoding="utf-8")


def embed_json(data):
    """JSON للتضمين داخل script: يُهرَّب منه '</' وفاصلا الأسطر كي لا يُغلق الوسم ولا يتصدّع النص."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def render(template, data, parts):
    """يملأ قالبًا: __CSS__ و__LIB__ من الملفات المشتركة، و__DATA__ من data، وباقي العلامات من parts. كل علامة مرة واحدة."""
    css, lib = assets()
    page = (SRC / template).read_text(encoding="utf-8")
    for token, value in (("__CSS__", css), ("__LIB__", lib), *parts.items(), ("__DATA__", embed_json(data))):
        assert token in page, token
        page = page.replace(token, value, 1)
    return page


def write(path, page):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(page)
    os.replace(tmp, path)
