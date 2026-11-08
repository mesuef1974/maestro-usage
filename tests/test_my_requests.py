"""«طلباتي»: الحال من requests/ والدفتر، والإلغاء قبل الالتقاط فقط، وإعادة المحاولة بالأصل وسبب الفشل."""
import http.client
import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import my_requests  # noqa: E402
import request_page  # noqa: E402
import serve  # noqa: E402

OK = {"title": "عنوان الطلب", "ask": "سطر أول\nسطر ثانٍ", "accept": "معيار حرّ", "size": "متوسط", "priority": "P2", "type": "خلل",
      "criteria": [1, 2], "page": "/x/", "files": ["templates/a.html"]}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_REQUESTS", str(tmp_path / "req"))
    (tmp_path / "req").mkdir()
    ledger = tmp_path / "events.jsonl"
    ledger.write_text("", encoding="utf-8")
    monkeypatch.setattr(request_page, "LEDGER_EVENTS", str(ledger))
    return tmp_path / "req", ledger


def _ledger(ledger, cid, title, ts, *events):
    rows = [{"ts": ts, "id": cid, "kind": "created", "data": {"problem": title, "state": "routed"}}]
    rows += [{"ts": ts, "id": cid, "kind": k, "data": d} for k, d in events]
    with open(ledger, "a", encoding="utf-8") as fh:
        fh.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def _pick(reqdir, name):
    (reqdir / (name + ".md")).rename(reqdir / (name + ".done"))


def test_pending_request_is_listed_and_cancellable(env):
    reqdir, _ = env
    name = request_page.submit(OK)["file"][:-3]
    [x] = my_requests.list_requests()
    assert x["name"] == name and x["status"] == "pending" and x["can_cancel"] and not x["can_retry"]
    my_requests.cancel(name)
    assert (reqdir / "cancelled" / (name + ".md")).is_file() and not (reqdir / (name + ".md")).exists()
    [x] = my_requests.list_requests()
    assert x["status"] == "cancelled" and x["can_retry"] and not x["can_cancel"]


def test_cancel_after_pickup_or_bad_name_is_refused(env):
    reqdir, _ = env
    name = request_page.submit(OK)["file"][:-3]
    _pick(reqdir, name)
    with pytest.raises(ValueError):
        my_requests.cancel(name)
    for bad in ("../x", "web-1", "", "web-20261105-120000/../../a"):
        with pytest.raises(ValueError):
            my_requests.cancel(bad)


def test_picked_request_shows_card_state_cost_and_failure_report(env):
    reqdir, ledger = env
    name = request_page.submit(OK)["file"][:-3]
    _pick(reqdir, name)
    _ledger(ledger, "W-OLD", OK["title"], "2000-01-01T00:00:00")  # أقدم من الإرسال: لا تُطابَق
    _ledger(ledger, "W-1", OK["title"], "2999-01-01T00:00:00",
            ("note", {"text": "[مشغّل] sonnet تشغيل 1: كلفة=0.25$ أدوار=9"}),
            ("note", {"text": "[مشغّل] sonnet تشغيل 2: كلفة=0.15$ أدوار=4"}),
            ("note", {"text": "[مشغّل] أُغلقت بتقرير: فشل ruff format"}),
            ("state", {"state": "closed"}))
    [x] = my_requests.list_requests()
    assert x["card"] == "W-1" and x["status"] == "failed" and abs(x["cost"] - 0.4) < 1e-9 and "ruff format" in x["label"] and x["can_retry"]


def test_retry_fields_rebuild_the_original_with_the_failure_reason(env):
    reqdir, ledger = env
    name = request_page.submit(OK)["file"][:-3]
    _pick(reqdir, name)
    _ledger(ledger, "W-2", OK["title"], "2999-01-01T00:00:00", ("note", {"text": "[مشغّل] أُغلقت بتقرير: السبب س"}), ("state", {"state": "closed"}))
    f = my_requests.retry_fields(name)
    assert f["title"] == OK["title"] and f["ask"].startswith("سطر أول\nسطر ثانٍ") and "W-2" in f["ask"] and "السبب س" in f["ask"]
    assert f["criteria"] == [1, 2] and f["accept"] == "معيار حرّ" and f["size"] == "متوسط" and f["retry_of"] == name
    assert f["files"] == ["templates/a.html"] and f["page"] == "/x/"
    assert len(f["ask"]) <= request_page.MAX["ask"]
    # الحقول تمرّ في التحقق نفسه، ومرجع الإعادة يُكتب في الملف الجديد
    sub = {k: v for k, v in f.items() if k in request_page.ALLOWED_KEYS}
    out = request_page.submit({**sub, "ask": f["ask"] + "أضفت الاختبار"})
    assert "إعادة لـ: " + name in (reqdir / out["file"]).read_text(encoding="utf-8")


def test_retry_of_must_be_a_request_name(env):
    with pytest.raises(request_page.ValidationError) as e:
        request_page.submit({**OK, "retry_of": "../../etc"})
    assert e.value.field == "retry_of"


@pytest.fixture()
def server(env):
    srv = serve.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def _req(port, method, path, origin=True):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Content-Length": "0"}
    if origin:
        h["Origin"] = "http://127.0.0.1:%d" % port
    c.request(method, path, headers=h)
    r = c.getresponse()
    out = r.status, json.loads(r.read().decode() or "{}")
    c.close()
    return out


def test_endpoints_list_cancel_and_retry(server, env):
    reqdir, _ = env
    name = request_page.submit(OK)["file"][:-3]
    st, j = _req(server, "GET", "/api/my_requests")
    assert st == 200 and j["requests"][0]["name"] == name
    assert _req(server, "POST", "/request/%s/cancel" % name, origin=False)[0] == 403  # بلا مصدر: مرفوض
    st, j = _req(server, "POST", "/request/%s/cancel" % name)
    assert st == 200 and j["ok"]
    assert _req(server, "POST", "/request/%s/cancel" % name)[0] == 409
    st, j = _req(server, "GET", "/api/my_requests/%s/retry" % name)
    assert st == 200 and j["fields"]["title"] == OK["title"]
    assert _req(server, "GET", "/api/my_requests/nope/retry")[0] == 400


def test_short_report_keeps_the_verdict_and_only_failed_checks():
    rep = "فشل النموذج بعد السلّم (كلفة=0.40$)؛ آخر سبب: ✔ حرّاس: نجح ✘ ruff format --check: فشل Would reformat: tests/t.py ✔ mypy: نجح"
    out = my_requests.short_report(rep)
    assert out.startswith("فشل النموذج") and "ruff format --check" in out and "mypy" not in out and "حرّاس" not in out
    assert my_requests.short_report("سبب بسيط") == "سبب بسيط"


def test_failed_checks_come_from_the_last_failure_log_note(env):
    reqdir, ledger = env
    name = request_page.submit(OK)["file"][:-3]
    _pick(reqdir, name)
    _ledger(ledger, "W-3", OK["title"], "2999-01-01T00:00:00",
            ("note", {"text": "[مشغّل] آخر سجلّ فشل: … ✔ ruff check: نجح ✘ ruff format --check: فشل Would reformat: tests/t.py ✔ mypy: نجح"}),
            ("note", {"text": "[مشغّل] أُغلقت بتقرير: فشل بعد السلّم؛ آخر سبب: ✔ حرّاس: نجح ✔ mypy ratchet: نجح لا"}),
            ("state", {"state": "closed"}))
    [x] = my_requests.list_requests()
    assert x["label"] == "أُغلق بتقرير: فشل بعد السلّم؛ الفاشل: ruff format --check: فشل Would reformat: tests/t.py"


def test_runner_caps_are_read_from_runner_py_without_importing_it(tmp_path):
    import runner_page

    src = tmp_path / "runner.py"
    src.write_text('raise SystemExit("لا يُنفَّذ")\nTOTAL_CAP_USD = 3.0\nDEFAULT_CONFIG = {"sizes": {"صغير": ["haiku", 15, 0.5], "كبير": ["sonnet", 80, 4.0]}}\n', encoding="utf-8")
    assert runner_page.caps(src) == {"total": 3.0, "sizes": {"صغير": 0.5, "كبير": 4.0}}
    src.write_text("X = 1\n", encoding="utf-8")
    assert runner_page.caps(src) == {}
    assert runner_page.caps(tmp_path / "missing.py") == {}


def test_retry_maps_legacy_types_to_known_ones():
    assert my_requests._known_type("إصلاح عيب") == "خلل"
    assert my_requests._known_type("ميزة") == "ميزة صغيرة"
    assert my_requests._known_type("خلل") == "خلل"
    assert my_requests._known_type("شيء آخر") == ""
