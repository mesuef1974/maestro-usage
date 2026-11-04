"""اختبارات استمارة «طلب جديد»: التحقق والكتابة الذرّية، وفحوص POST /request (المرحلة 0 من أمر العمل)."""
import http.client
import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import request_page  # noqa: E402
import serve  # noqa: E402

OK = {"title": "عنوان الطلب", "ask": "م", "accept": "أ\nب", "size": "صغير", "priority": "P2", "touches": ["الأمن"]}


@pytest.fixture()
def reqdir(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_REQUESTS", str(tmp_path))
    return tmp_path


def test_valid_request_is_written_in_the_intake_template_with_provenance(reqdir):
    out = request_page.submit(OK)
    text = (reqdir / out["file"]).read_text(encoding="utf-8")
    for key in ("العنوان: عنوان الطلب", "المطلوب: م", "معايير القبول: أ ؛ ب", "الوسم: صغير", "الأولوية: P2", "يمسّ: الأمن",
                "المصدر: mizan-form", "sha256: ", "مقدَّم في: "):
        assert key in text
    assert not list((reqdir / ".incoming").iterdir())  # لا ملف مؤقت باقٍ: الكتابة ذرّية


@pytest.mark.parametrize("bad,field", [({"title": ""}, "title"), ({"ask": ""}, "ask"), ({"accept": "  "}, "accept"),
                                       ({"size": "ضخم"}, "size"), ({"priority": ""}, "priority"), ({"priority": "P0"}, "priority"),
                                       ({"touches": ["شيء"]}, "touches"), ({"extra": "x"}, "extra")])
def test_invalid_fields_are_rejected_with_field_name_and_no_file(reqdir, bad, field):
    with pytest.raises(request_page.ValidationError) as e:
        request_page.submit({**OK, **bad})
    assert e.value.field == field
    assert not [p for p in reqdir.iterdir() if p.is_file()]


def test_priority_is_never_filled_silently(reqdir):
    body = {k: v for k, v in OK.items() if k != "priority"}
    with pytest.raises(request_page.ValidationError) as e:
        request_page.submit(body)
    assert e.value.field == "priority"


def test_personal_data_is_rejected(reqdir):
    with pytest.raises(request_page.ValidationError) as e:
        request_page.submit({**OK, "ask": "الطالب رقمه 29250000000 يحتاج"})
    assert e.value.field == "ask"
    with pytest.raises(request_page.ValidationError):
        request_page.submit({**OK, "title": "راسل a@b.com"})


def test_two_requests_in_the_same_second_do_not_overwrite(reqdir):
    import time
    t = time.localtime()
    assert request_page.submit(OK, t)["file"] != request_page.submit(OK, t)["file"]


def test_rate_limit_window():
    now = [0.0]
    rl = request_page.RateLimit(2, clock=lambda: now[0])
    assert rl.allow() and rl.allow() and not rl.allow()
    now[0] = 3601
    assert rl.allow()


@pytest.fixture()
def server(reqdir):
    srv = serve.make_server(0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield port
    srv.shutdown()


def _post(port, body, headers=None, host=None, raw_len=True):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    h = {"Content-Type": "application/json", "Origin": "http://127.0.0.1:%d" % port, "Host": host or "127.0.0.1:%d" % port}
    h.update(headers or {})
    h = {k: v for k, v in h.items() if v is not None}
    c.putrequest("POST", "/request", skip_host=True, skip_accept_encoding=True)
    for k, v in h.items():
        c.putheader(k, v)
    if raw_len:
        c.putheader("Content-Length", str(len(data)))
    c.endheaders(data)
    r = c.getresponse()
    out = r.status, json.loads(r.read().decode() or "{}")
    c.close()
    return out


def test_post_ok_writes_one_file(server, reqdir):
    status, out = _post(server, OK)
    assert status == 200 and out["ok"] and len([p for p in reqdir.iterdir() if p.is_file()]) == 1


def test_post_wrong_or_missing_origin_or_host_is_403_and_writes_nothing(server, reqdir):
    for hdr in ({"Origin": "http://evil.example"}, {"Origin": None}):
        assert _post(server, OK, hdr)[0] == 403
    assert _post(server, OK, host="evil.example")[0] == 403
    assert not [p for p in reqdir.iterdir() if p.is_file()]


def test_post_wrong_content_type_is_415(server):
    assert _post(server, OK, {"Content-Type": "text/plain"})[0] == 415


def test_post_without_content_length_is_411(server):
    assert _post(server, OK, raw_len=False)[0] == 411


def test_post_over_the_cap_is_413_before_reading_the_body(server):
    status, _ = _post(server, b"x" * (request_page.MAX_BODY + 1))
    assert status == 413


def test_post_field_error_returns_arabic_message_and_field(server):
    status, out = _post(server, {**OK, "title": ""})
    assert status == 400 and out["field"] == "title" and "العنوان" in out["error"]


def test_post_rate_limit_is_429(server):
    codes = [_post(server, OK)[0] for _ in range(request_page.RATE_PER_HOUR + 1)]
    assert codes[:-1] == [200] * request_page.RATE_PER_HOUR and codes[-1] == 429


def test_approval_defaults_by_size_and_is_written(reqdir):
    t = lambda p: (reqdir / request_page.submit(p)["file"]).read_text(encoding="utf-8")  # noqa: E731
    assert "الاعتماد: مباشر" in t(OK)
    assert "الاعتماد: معاينة" in t({**OK, "size": "تصميم"})
    assert "الاعتماد: معاينة" in t({**OK, "approval": "معاينة"})


def test_invalid_approval_is_rejected(reqdir):
    with pytest.raises(request_page.ValidationError) as e:
        request_page.submit({**OK, "approval": "فوري"})
    assert e.value.field == "approval"
