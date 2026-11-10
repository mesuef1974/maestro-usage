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

OK = {"title": "عنوان الطلب", "ask": "م", "accept": "أ\nب", "size": "صغير", "priority": "P2", "touches": ["الأمن"], "type": "خلل", "criteria": [1], "page": "/x/"}


@pytest.fixture()
def reqdir(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_REQUESTS", str(tmp_path))
    return tmp_path


def test_valid_request_is_written_in_the_intake_template_with_provenance(reqdir):
    out = request_page.submit(OK)
    text = (reqdir / out["file"]).read_text(encoding="utf-8")
    for key in ("العنوان: عنوان الطلب", "المطلوب: م", "معايير القبول: make prepush ينجح ؛ أ ؛ ب", "الوسم: صغير", "الأولوية: P2", "يمسّ: الأمن",
                "المصدر: mizan-form", "sha256: ", "مقدَّم في: "):
        assert key in text
    assert not list((reqdir / ".incoming").iterdir())  # لا ملف مؤقت باقٍ: الكتابة ذرّية


@pytest.mark.parametrize("bad,field", [({"title": ""}, "title"), ({"ask": ""}, "ask"), ({"accept": "  ", "criteria": []}, "criteria"),
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
    assert request_page.submit(OK, t)["file"] != request_page.submit({**OK, "title": OK["title"] + " ثانٍ"}, t)["file"]


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
    codes = [_post(server, {**OK, "title": "%s %d" % (OK["title"], i)})[0] for i in range(request_page.RATE_PER_HOUR + 1)]  # عنوانٌ لكلّ طلب: حاجزُ التكرار يرفض المكرَّر قبل الحدّ
    assert codes[:-1] == [200] * request_page.RATE_PER_HOUR and codes[-1] == 429


def test_approval_defaults_by_size_and_is_written(reqdir):
    t = lambda p: (reqdir / request_page.submit(p)["file"]).read_text(encoding="utf-8")  # noqa: E731
    assert "الاعتماد: مباشر" in t(OK)
    assert "الاعتماد: معاينة" in t({**OK, "title": OK["title"] + " تصميم", "size": "تصميم"})
    assert "الاعتماد: معاينة" in t({**OK, "title": OK["title"] + " معاينة", "approval": "معاينة"})


def test_invalid_approval_is_rejected(reqdir):
    with pytest.raises(request_page.ValidationError) as e:
        request_page.submit({**OK, "approval": "فوري"})
    assert e.value.field == "approval"


def test_pii_fallback_matches_ledger_when_present(monkeypatch):
    """النسخة الاحتياطية مطابقة لتعبير السجلّ؛ وبغياب السجلّ تعمل الصفحة بها لا بالخطأ."""
    request_page._PII = None
    monkeypatch.setenv("MAESTRO_LEDGER", "/nonexistent/ledger.py")
    assert request_page.pii_pattern().pattern == request_page._PII_FALLBACK.pattern
    assert request_page.PII_SOURCE == "fallback"
    request_page._PII = None
    monkeypatch.delenv("MAESTRO_LEDGER")
    src = request_page.ledger_source()
    if not src.is_file():
        pytest.skip("سجلّ المايسترو غير موجود هنا")
    assert request_page.pii_pattern().pattern == request_page._PII_FALLBACK.pattern
    assert request_page.PII_SOURCE == "ledger"


# ───────── المرحلة 2: النوع والمعايير والنطاق والجاهزية والمعاينة وكشف التكرار ─────────
FULL = {"title": "زر الحفظ لا يعمل في صفحة الحضور", "type": "خلل", "ask": "ماذا يحدث؟ لا شيء\nما المتوقَّع؟ يُحفظ",
        "criteria": [1, 2, 3, 4], "accept": "", "size": "صغير", "priority": "P2", "page": "/attendance/",
        "files": ["attendance/views.py", "templates/attendance/form.html"], "out_of_scope": "التقارير"}


def test_type_is_required_and_criteria_ids_map_to_text(reqdir):
    with pytest.raises(request_page.ValidationError) as e:
        request_page.submit({**FULL, "type": ""})
    assert e.value.field == "type"
    text = (reqdir / request_page.submit(FULL)["file"]).read_text(encoding="utf-8")
    lib = request_page.criteria_lib()["by_id"]
    assert "معايير القبول: " + " ؛ ".join(lib[i]["text"] for i in (1, 2, 3, 4)) in text
    for line in ("النوع: خلل", "معايير مرقّمة: 1، 2، 3، 4", "فحوص المشغّل: tests_in_diff، scope_only، no_migrations",
                 "الصفحة: /attendance/", "الملفات: attendance/views.py، templates/attendance/form.html", "خارج النطاق: التقارير"):
        assert line in text, line
    assert "المطلوب: ماذا يحدث؟ لا شيء / ما المتوقَّع؟ يُحفظ" in text  # الأسطر تبقى مفصولة في سطر واحد


@pytest.mark.parametrize("bad,field", [({"criteria": [99]}, "criteria"), ({"criteria": ["1"]}, "criteria"), ({"criteria": [True]}, "criteria"),
                                       ({"criteria": [], "accept": ""}, "criteria"), ({"files": ["../etc/passwd"]}, "files"),
                                       ({"files": ["a b.py"]}, "files"), ({"files": ["f%d.py" % i for i in range(21)]}, "files"),
                                       ({"size": "ضخم"}, "size"), ({"page": "راسل a@b.com"}, "page")])
def test_phase2_fields_are_validated(reqdir, bad, field):
    with pytest.raises(request_page.ValidationError) as e:
        request_page.submit({**FULL, **bad})
    assert e.value.field == field


def test_declared_forbidden_file_adds_the_touch_automatically(reqdir):
    out = request_page.submit({**FULL, "files": ["core/migrations/0042_x.py", "app/security/auth.py"]})
    assert out["auto_touches"] == ["الأمن", "الهجرات"]
    text = (reqdir / out["file"]).read_text(encoding="utf-8")
    assert "يمسّ: الأمن، الهجرات" in text


def test_touch_globs_match_the_merge_gate():
    """مصدر واحد: اتحاد أنماط «يمسّ» يساوي FORBIDDEN_GLOBS في بوّابة الدمج إن وُجد مستودع المنصّة."""
    import ast
    gate = request_page.REPO / "scripts" / "auto_merge_gate.py"
    if not gate.is_file():
        pytest.skip("مستودع المنصّة غير موجود هنا")
    tree = ast.parse(gate.read_text(encoding="utf-8"))
    globs = next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "FORBIDDEN_GLOBS" for t in n.targets))
    assert set(globs) == {g for v in request_page.TOUCH_GLOBS.values() for g in v}


def test_legacy_design_size_still_accepted_and_defaults_to_preview(reqdir):
    text = (reqdir / request_page.submit({**FULL, "size": "تصميم"})["file"]).read_text(encoding="utf-8")
    assert "الوسم: تصميم" in text and "الاعتماد: معاينة" in text
    text = (reqdir / request_page.submit({**FULL, "title": FULL["title"] + " واجهة", "type": "تحسين واجهة"})["file"]).read_text(encoding="utf-8")
    assert "الاعتماد: معاينة" in text  # افتراضي النوع


def test_default_criteria_per_type_match_the_workorder():
    lib = request_page.criteria_lib()
    want = {"خلل": [1, 2, 3, 4], "تحسين واجهة": [1, 3, 4, 7, 8, 9, 11, 12, 13], "ميزة صغيرة": [1, 2, 3, 4, 5, 6], "نص ومحتوى": [1, 3, 11]}
    for t, ids in want.items():
        assert [c["id"] for c in lib["criteria"] if t in c["types"]] == ids, t
    assert {c["verify"]["check"] for c in lib["criteria"] if c["verify"].get("auto") == "runner"} == {"tests_in_diff", "scope_only", "no_migrations"}


def test_readiness_notes_do_not_block():
    f = request_page.validate({**FULL, "type": "ميزة صغيرة", "title": "زر", "ask": "قصير", "criteria": [1], "page": "", "files": []})
    notes = request_page.readiness(f)
    assert len(notes) == 3  # العنوان والطول والمعيار الواحد؛ النطاق صار شرطًا صلبًا للخلل وتحسين الواجهة
    assert request_page.readiness(request_page.validate({**FULL, "ask": "و" * 130})) == []


def test_preview_writes_nothing(reqdir):
    out = request_page.preview(FULL)
    assert out["ok"] and out["body"].startswith("العنوان: ") and "النوع: خلل" in out["body"]
    assert not [p for p in reqdir.iterdir() if p.is_file()]


def test_similar_titles_from_open_cards():
    cards = [{"id": "W-1", "title": "زرّ الحفظ لا يعمل في صفحة الحضور والغياب", "state": "routed"},
             {"id": "W-2", "title": "تحسين ألوان التقارير", "state": "routed"}]
    hits = request_page.similar("زر الحفظ لا يعمل بصفحة الحضور", cards)
    assert [h["id"] for h in hits] == ["W-1"]
    assert request_page.similar("كلمة", cards) == []


def test_open_cards_reads_ledger_and_skips_closed(tmp_path):
    import json
    p = tmp_path / "events.jsonl"
    rows = [{"id": "W-1", "kind": "created", "data": {"problem": "أ ب ج"}}, {"id": "W-1", "kind": "state", "data": {"state": "routed"}},
            {"id": "W-2", "kind": "created", "data": {"problem": "د ه و"}}, {"id": "W-2", "kind": "state", "data": {"state": "closed"}}]
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\nnot json\n", encoding="utf-8")
    assert [c["id"] for c in request_page.open_cards(p)] == ["W-1"]


def test_match_files_all_words_shortest_first():
    files = ["attendance/views.py", "attendance/tests/test_views.py", "core/views.py"]
    assert request_page.match_files("attendance views", files) == ["attendance/views.py", "attendance/tests/test_views.py"]
    assert request_page.match_files("", files) == []


def test_preview_and_api_endpoints(server):
    port = server
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    data = json.dumps(FULL).encode()
    c.request("POST", "/request/preview", body=data, headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:%d" % port,
                                                              "Host": "127.0.0.1:%d" % port, "Content-Length": str(len(data))})
    r = c.getresponse()
    j = json.loads(r.read())
    assert r.status == 200 and "النوع: خلل" in j["body"]
    for path in ("/api/files?q=views", "/api/similar?title=%D8%B2%D8%B1+%D8%A7%D9%84%D8%AD%D9%81%D8%B8"):
        c.request("GET", path, headers={"Host": "127.0.0.1:%d" % port})
        r = c.getresponse()
        assert r.status == 200 and isinstance(json.loads(r.read()), dict)
    c.request("GET", "/api/files?q=x", headers={"Host": "evil:1"})
    r = c.getresponse()
    r.read()
    assert r.status == 403
    c.close()


def test_template_headings_alone_are_rejected(reqdir):
    tpl = request_page.criteria_lib()["types"]["تحسين واجهة"]["template"]
    with pytest.raises(request_page.ValidationError) as e:
        request_page.submit({**FULL, "type": "تحسين واجهة", "ask": tpl})
    assert e.value.field == "ask"
    ok = tpl.replace("الوضع الحالي:", "الوضع الحالي: الزر رمادي باهت لا يُرى على الخلفية")
    assert request_page.submit({**FULL, "type": "تحسين واجهة", "ask": ok})["ok"]


def test_upload_endpoint_guards_and_stages(server, tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_ATTACHMENTS", str(tmp_path / "att"))
    port = server
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    def up(body, ctype="multipart/form-data; boundary=B", origin=True, length=True):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.putrequest("POST", "/request/upload", skip_host=True, skip_accept_encoding=True)
        c.putheader("Host", "127.0.0.1:%d" % port)
        if origin:
            c.putheader("Origin", "http://127.0.0.1:%d" % port)
        c.putheader("Content-Type", ctype)
        if length:
            c.putheader("Content-Length", str(len(body)))
        c.endheaders()
        c.send(body)
        r = c.getresponse()
        out = (r.status, json.loads(r.read() or b"{}"))
        c.close()
        return out

    part = lambda confirm: ((b"--B\r\nContent-Disposition: form-data; name=\"confirm\"\r\n\r\n1\r\n" if confirm else b"")  # noqa: E731
                            + b"--B\r\nContent-Disposition: form-data; name=\"files\"; filename=\"../../a.png\"\r\n\r\n" + png + b"\r\n--B--\r\n")
    code, j = up(part(True))
    assert code == 200 and j["files"][0]["name"] == "a.png" and len(j["token"]) == 16
    assert up(part(False))[0] == 400  # بلا تأكيد
    assert up(part(True), origin=False)[0] == 403
    assert up(part(True), ctype="application/json")[0] == 415
    assert up(part(True), length=False)[0] == 411


def test_bug_needs_a_checkbox_criterion_and_scope(reqdir):
    with pytest.raises(request_page.ValidationError) as e:
        request_page.submit({**FULL, "criteria": [], "accept": "سطر حرّ وحده"})
    assert e.value.field == "criteria"
    with pytest.raises(request_page.ValidationError) as e:
        request_page.submit({**FULL, "page": "", "files": []})
    assert e.value.field == "page"
    assert request_page.submit({**FULL, "type": "ميزة صغيرة", "page": "", "files": []})["ok"]  # الميزة لا تشترط النطاق


def test_recently_closed_with_report_counts_as_similar(tmp_path):
    import json
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+03:00")
    rows = [{"id": "W-9", "ts": now, "kind": "created", "data": {"problem": "ملف البي دي اف في الزيارة الصفية"}},
            {"id": "W-9", "ts": now, "kind": "note", "data": {"text": "[مشغّل] أُغلقت بتقرير: فشل النموذج بعد السلّم الكامل"}},
            {"id": "W-9", "ts": now, "kind": "state", "data": {"state": "closed"}},
            {"id": "W-8", "ts": "2020-01-01T00:00:00+03:00", "kind": "created", "data": {"problem": "ملف البي دي اف في الزيارة"}},
            {"id": "W-8", "ts": "2020-01-01T00:00:00+03:00", "kind": "note", "data": {"text": "[مشغّل] أُغلقت بتقرير: قديم"}},
            {"id": "W-8", "ts": "2020-01-01T00:00:00+03:00", "kind": "state", "data": {"state": "closed"}}]
    p = tmp_path / "events.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    hits = request_page.similar("ملف PDF الزيارة الصفية", request_page.open_cards(p))
    assert [h["id"] for h in hits] == ["W-9"] and hits[0]["report"].startswith("فشل النموذج")


def test_depends_on_is_validated_and_written_for_the_runner(reqdir):
    out = request_page.submit({**OK, "depends_on": "W-20261109-001، W-20261109-002"})
    assert "يعتمد على: W-20261109-001، W-20261109-002" in (reqdir / out["file"]).read_text(encoding="utf-8")
    with pytest.raises(request_page.ValidationError) as e:
        request_page.validate({**OK, "depends_on": "001"})
    assert e.value.field == "depends_on"
