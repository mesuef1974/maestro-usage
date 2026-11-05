"""مرفقات «طلب جديد» (المرحلة 1): رفعٌ منفصل multipart، فحصٌ بالبايتات الأولى، حدودٌ صلبة، وأسماءٌ آمنة.

المسار: POST /request/upload (ملف واحد أو أكثر + تأكيد PDPPL) ← مجلد مؤقت requests_attachments/.staging/<رمز>/ يعيد رمزه؛
ثم POST /request بالحقل attachments=<الرمز> ← ينقل المجلد إلى requests_attachments/<اسم ملف الطلب>/ ويكتب في الطلب سطر «المرفقات».
المرفقات خارج أي مستودع (requests_attachments/ في .gitignore بمستودع الحوكمة)، ولا تُحذف إلا بعد RETENTION_DAYS.
"""
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import time
import zipfile
from email.parser import BytesParser
from email.policy import HTTP
from pathlib import Path

MAX_FILES = 6
MAX_FILE = 10 * 1024 * 1024
MAX_TOTAL = 25 * 1024 * 1024
MAX_BODY = MAX_TOTAL + 512 * 1024  # جسم multipart: المحتوى + رؤوس الأجزاء
STAGING_TTL = 24 * 3600  # رفعٌ لم يُربط بطلب خلال يوم يُزال
RETENTION_DAYS = 30
CONFIRM_TEXT = "أؤكّد أن المرفقات خالية من بيانات شخصية للطلبة والمعلّمين (PDPPL)"

# النوع ← (الامتدادات، فاحص البايتات، كيف يصل إلى النموذج)
KINDS = {
    "image": (("png", "jpg", "jpeg", "webp"), "الصورة كما هي"),
    "pdf": (("pdf",), "المستند كما هو"),
    "sheet": (("xlsx", "csv"), "ملخّص: الأوراق والأعمدة وأول 20 صفًّا"),
    "text": (("md", "txt"), "النص كما هو"),
}
EXT_KIND = {e: k for k, (exts, _v) in KINDS.items() for e in exts}
MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "csv": "text/csv", "md": "text/markdown", "txt": "text/plain"}


class UploadError(ValueError):
    def __init__(self, message, name="", code=400):
        super().__init__(message)
        self.name, self.code = name, code


def base_dir():
    return Path(os.environ.get("RUNNER_ATTACHMENTS") or Path.home() / "delivery_manager_work" / "requests_attachments")


def safe_name(name, taken=()):
    """اسم الملف وحده بأحرف آمنة، ≤ 80 حرفًا، بلا تكرار؛ ../../x.png ← x.png."""
    name = re.split(r"[\\/]", str(name or ""))[-1].strip().replace("\x00", "")
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = re.sub(r"[^\w\-؀-ۿ]+", "-", stem).strip("-.") or "ملف"
    ext = re.sub(r"[^a-z0-9]", "", ext.lower())
    out = (stem[: 80 - len(ext) - 1] + "." + ext) if ext else stem[:80]
    n, base = 2, out
    while out in taken:
        s, _d, e = base.rpartition(".")
        out = "%s-%d.%s" % (s, n, e) if e else "%s-%d" % (base, n)
        n += 1
    return out


def _utf8_text(data):
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def sniff(ext, data):
    """يتحقق أن البايتات الأولى تطابق الامتداد؛ يعيد النص المستخرج للفحص (أو "" لما لا نصّ فيه) أو يرفع UploadError."""
    kind = EXT_KIND.get(ext)
    if not kind:
        raise UploadError("نوع غير مسموح (المسموح: صور png/jpg/webp، وpdf، وxlsx/csv، وmd/txt)")
    head = data[:16]
    if ext == "png" and not head.startswith(b"\x89PNG\r\n\x1a\n"):
        raise UploadError("ليس PNG حقيقيًّا")
    if ext in ("jpg", "jpeg") and not head.startswith(b"\xff\xd8\xff"):
        raise UploadError("ليس JPEG حقيقيًّا")
    if ext == "webp" and not (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
        raise UploadError("ليس WEBP حقيقيًّا")
    if ext == "pdf":
        if not head.startswith(b"%PDF-"):
            raise UploadError("ليس PDF حقيقيًّا")
        return ""
    if ext == "xlsx":
        if not head.startswith(b"PK\x03\x04"):
            raise UploadError("ليس XLSX حقيقيًّا")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
                if not any(n.startswith("xl/") for n in names):
                    raise UploadError("ليس XLSX حقيقيًّا (لا مجلّد xl/)")
                parts = [n for n in names if n == "xl/sharedStrings.xml" or (n.startswith("xl/worksheets/") and n.endswith(".xml"))]
                total, texts = 0, []
                for n in parts:  # نصوص الخلايا للفحص فقط؛ سقف يمنع قنبلة الضغط
                    info = z.getinfo(n)
                    total += info.file_size
                    if total > 50 * 1024 * 1024:
                        raise UploadError("محتوى XLSX مفكوكًا أكبر من 50MB")
                    texts.append(re.sub(r"<[^>]+>", " ", z.read(n).decode("utf-8", "replace")))
                return " ".join(texts)
        except zipfile.BadZipFile:
            raise UploadError("ملف XLSX تالف") from None
    if kind in ("text", "sheet"):  # md وtxt وcsv
        t = _utf8_text(data)
        if t is None:
            raise UploadError("نص غير صالح (يجب UTF-8 بلا بايت صفري)")
        return t
    return ""  # الصور: لا فحص نصّي، والتأكيد يكفي


def sheet_summary(ext, data, rows=20):
    """ملخّص بلا توكنز لجدول: الأوراق والأعمدة وأول rows صفًّا (csv مباشرة، xlsx من XML)."""
    if ext == "csv":
        import csv
        r = list(csv.reader(io.StringIO(_utf8_text(data) or "")))
        return {"sheets": [{"name": "csv", "rows": len(r), "head": r[: rows + 1]}]}
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            shared = [re.sub(r"<[^>]+>", "", si) for si in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8", "replace"), re.S)]
        for n in sorted(x for x in z.namelist() if x.startswith("xl/worksheets/sheet") and x.endswith(".xml")):
            xml = z.read(n).decode("utf-8", "replace")
            table = []
            for row in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S):
                cells = []
                for attrs, v in re.findall(r"<c([^>]*)>(?:.*?<v>(.*?)</v>)?", row, re.S):
                    cells.append(shared[int(v)] if 't="s"' in attrs and v.isdigit() and int(v) < len(shared) else v)
                table.append(cells)
            out.append({"name": n.rsplit("/", 1)[-1][:-4], "rows": len(table), "head": table[: rows + 1]})
    return {"sheets": out}


def parse_multipart(content_type, body):
    """يحلّل multipart/form-data بمحلّل البريد في المكتبة القياسية (وحدة cgi أُزيلت في بايثون 3.13)."""
    msg = BytesParser(policy=HTTP).parsebytes(b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + body)
    if not msg.is_multipart():
        raise UploadError("الجسم ليس multipart/form-data", code=415)
    fields, files = {}, []
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        fname = part.get_filename()
        data = part.get_payload(decode=True) or b""
        if fname is not None:
            files.append((fname, data))
        elif name:
            fields[name] = data.decode("utf-8", "replace")
    return fields, files


def stage(fields, files, pii=None, now=None):
    """يتحقق من كل ملف ويحفظه في مجلد مؤقت؛ يعيد {token, files:[…]} أو يرفع UploadError (لا يُحفظ شيء عند أي رفض)."""
    if not files:
        raise UploadError("لا ملفات في الطلب")
    if fields.get("confirm") != "1":
        raise UploadError("أكّد أن المرفقات خالية من بيانات شخصية للطلبة والمعلّمين (PDPPL)")
    if len(files) > MAX_FILES:
        raise UploadError("%d ملفات على الأكثر" % MAX_FILES)
    total, taken, out = 0, set(), []
    for fname, data in files:
        nm = safe_name(fname, taken)
        ext = nm.rpartition(".")[2] if "." in nm else ""
        if len(data) > MAX_FILE:
            raise UploadError("أكبر من 10MB", nm, 413)
        if not data:
            raise UploadError("ملف فارغ", nm)
        total += len(data)
        if total > MAX_TOTAL:
            raise UploadError("مجموع المرفقات أكبر من 25MB", nm, 413)
        try:
            text = sniff(ext, data)
        except UploadError as exc:
            raise UploadError(str(exc), nm, exc.code) from None
        if pii is not None and text and pii.search(text):
            raise UploadError("يبدو في الملف رقم هوية أو بريد؛ تُمنع البيانات الشخصية", nm)
        taken.add(nm)
        out.append({"name": nm, "type": MIME.get(ext, "application/octet-stream"), "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(), "view": KINDS[EXT_KIND[ext]][1], "_data": data, "_ext": ext})
    token = secrets.token_hex(8)
    d = base_dir() / ".staging" / token
    d.mkdir(parents=True, exist_ok=True)
    meta = []
    for f in out:
        (d / f["name"]).write_bytes(f["_data"])
        if EXT_KIND[f["_ext"]] == "sheet":
            (d / (f["name"] + ".summary.json")).write_text(json.dumps(sheet_summary(f["_ext"], f["_data"]), ensure_ascii=False), encoding="utf-8")
        meta.append({k: v for k, v in f.items() if not k.startswith("_")})
    (d / "attachments.json").write_text(json.dumps({"confirmed": CONFIRM_TEXT, "staged_at": int(now or time.time()), "files": meta},
                                                   ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "token": token, "files": meta}


def bind(token, request_stem):
    """ينقل مجلد الرفع المؤقت إلى requests_attachments/<اسم الطلب>/ ويعيد قائمة الملفات؛ رمز غير صالح ← UploadError."""
    if not re.fullmatch(r"[0-9a-f]{16}", str(token or "")):
        raise UploadError("رمز المرفقات غير صالح")
    src = base_dir() / ".staging" / token
    if not (src / "attachments.json").is_file():
        raise UploadError("انتهت صلاحية المرفقات أو لم تُرفع؛ أعد إرفاقها")
    meta = json.loads((src / "attachments.json").read_text(encoding="utf-8"))
    dst = base_dir() / request_stem
    os.replace(src, dst)
    return dst, meta["files"]


def cleanup(now=None):
    """يزيل الرفع المؤقت الأقدم من يوم، ومرفقات الطلبات الأقدم من RETENTION_DAYS؛ يعيد عدد المجلدات المزالة."""
    now = now or time.time()
    n, root = 0, base_dir()
    for d, ttl in [(p, STAGING_TTL) for p in (root / ".staging").glob("*")] + [(p, RETENTION_DAYS * 86400) for p in root.glob("web-*")]:
        try:
            if d.is_dir() and now - d.stat().st_mtime > ttl:
                shutil.rmtree(d)
                n += 1
        except OSError:
            continue
    return n
