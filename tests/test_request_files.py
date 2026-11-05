"""المرفقات (المرحلة 1): الأنواع الأربعة تُقبل بالبايتات الحقيقية، والمتنكّر وSVG يُرفضان، والحدود صلبة، والأسماء آمنة."""
import io
import json
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import request_files as rf  # noqa: E402
import request_page  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 32
PDF = b"%PDF-1.7\n%..." + b"\x00" * 32


def xlsx(cells=("اسم", "قيمة")):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/sharedStrings.xml", "<sst>" + "".join("<si><t>%s</t></si>" % c for c in cells) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                                               '<row r="2"><c r="A2"><v>5</v></c></row></sheetData></worksheet>')
    return buf.getvalue()


@pytest.fixture()
def adir(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_ATTACHMENTS", str(tmp_path / "att"))
    monkeypatch.setenv("RUNNER_REQUESTS", str(tmp_path / "req"))
    return tmp_path / "att"


OK = {"confirm": "1"}


def test_four_kinds_are_accepted_by_real_bytes(adir):
    files = [("a.png", PNG), ("b.jpg", JPG), ("c.webp", WEBP), ("d.pdf", PDF), ("e.xlsx", xlsx()), ("f.md", "# عنوان\nنص".encode())]
    out = rf.stage(OK, files)
    assert [f["name"] for f in out["files"]] == ["a.png", "b.jpg", "c.webp", "d.pdf", "e.xlsx", "f.md"]
    d = adir / ".staging" / out["token"]
    assert (d / "e.xlsx.summary.json").is_file()
    s = json.loads((d / "e.xlsx.summary.json").read_text(encoding="utf-8"))
    assert s["sheets"][0]["head"][0] == ["اسم", "قيمة"] and s["sheets"][0]["rows"] == 2
    assert all(len(f["sha256"]) == 64 for f in out["files"])


@pytest.mark.parametrize("name,data", [("evil.png", b"MZ\x90\x00" + b"\x00" * 60), ("x.svg", b"<svg/>"), ("x.html", b"<html>"),
                                       ("x.zip", b"PK\x03\x04"), ("x.exe", b"MZ"), ("fake.xlsx", b"PK\x03\x04garbage"),
                                       ("bin.txt", b"a\x00b"), ("bad.csv", b"\xff\xfe\x00")])
def test_disguised_and_forbidden_files_are_rejected(adir, name, data):
    with pytest.raises(rf.UploadError):
        rf.stage(OK, [(name, data)])
    assert not (adir / ".staging").exists() or not list((adir / ".staging").iterdir())


def test_limits(adir, monkeypatch):
    with pytest.raises(rf.UploadError) as e:
        rf.stage(OK, [("big.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * (rf.MAX_FILE + 1))])
    assert e.value.code == 413
    with pytest.raises(rf.UploadError):
        rf.stage(OK, [("p%d.png" % i, PNG) for i in range(7)])
    monkeypatch.setattr(rf, "MAX_TOTAL", 100)
    with pytest.raises(rf.UploadError) as e:
        rf.stage(OK, [("a.png", PNG), ("b.png", PNG)])
    assert e.value.code == 413


def test_confirmation_is_required(adir):
    with pytest.raises(rf.UploadError):
        rf.stage({}, [("a.png", PNG)])


def test_names_are_sanitized_and_unique():
    assert rf.safe_name("../../x.png") == "x.png"
    assert rf.safe_name("C:\\a\\b\\لقطة شاشة!.PNG") == "لقطة-شاشة.png"
    assert rf.safe_name("x.png", {"x.png"}) == "x-2.png"
    assert len(rf.safe_name("ا" * 200 + ".png")) <= 80


def test_personal_data_in_text_files_is_rejected(adir):
    pii = request_page._PII_FALLBACK
    for name, data in (("n.md", "الطالب 29250000000".encode()), ("s.csv", "اسم,بريد\nأ,a@b.com".encode()), ("x.xlsx", xlsx(("29250000000", "ب")))):
        with pytest.raises(rf.UploadError) as e:
            rf.stage(OK, [(name, data)], pii)
        assert e.value.name == name


def test_multipart_parse():
    body = (b"--B\r\nContent-Disposition: form-data; name=\"confirm\"\r\n\r\n1\r\n"
            b"--B\r\nContent-Disposition: form-data; name=\"files\"; filename=\"a.png\"\r\nContent-Type: image/png\r\n\r\n" + PNG + b"\r\n--B--\r\n")
    fields, files = rf.parse_multipart("multipart/form-data; boundary=B", body)
    assert fields == {"confirm": "1"} and files == [("a.png", PNG)]


def test_submit_binds_attachments_and_writes_lines(adir):
    out = rf.stage(OK, [("a.png", PNG)])
    full = {"title": "زر الحفظ لا يعمل في صفحة الحضور", "type": "خلل", "ask": "ماذا يحدث؟ لا يحفظ الزر شيئًا عند الضغط", "criteria": [1, 3],
            "size": "صغير", "priority": "P2", "attachments": out["token"]}
    res = request_page.submit(full)
    assert res["attachments"] == 1
    text = (adir.parent / "req" / res["file"]).read_text(encoding="utf-8")
    stem = res["file"][:-3]
    assert "المرفقات: %s" % (adir / stem) in text
    assert "ملفات المرفقات: a.png|" + out["files"][0]["sha256"] in text
    assert (adir / stem / "a.png").read_bytes() == PNG and not (adir / ".staging" / out["token"]).exists()
    with pytest.raises(request_page.ValidationError) as e:  # الرمز يُستعمل مرة واحدة
        request_page.submit(full)
    assert e.value.field == "attachments"


def test_cleanup_removes_old_staging_and_expired(adir):
    out = rf.stage(OK, [("a.png", PNG)])
    (adir / "web-20260101-000000").mkdir(parents=True)
    assert rf.cleanup(now=10 ** 12) == 2
    assert not (adir / ".staging" / out["token"]).exists()
