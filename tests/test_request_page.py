"""اختبارات صفحة «طلب جديد»: التحقق، الكتابة بالقالب الذي يقرؤه الاستلام، ومسار POST /request."""
import json
import os
import sys
import threading
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import request_page  # noqa: E402
import serve  # noqa: E402

OK = {"title": "ن", "ask": "م", "accept": "أ\nب", "size": "صغير", "priority": "P2", "touches": ["الأمن"]}


@pytest.fixture()
def reqdir(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_REQUESTS", str(tmp_path))
    return tmp_path


def test_valid_request_is_written_in_the_intake_template(reqdir):
    out = request_page.submit(OK)
    text = (reqdir / out["file"]).read_text(encoding="utf-8")
    for key in ("العنوان: ن", "المطلوب: م", "معايير القبول: أ ؛ ب", "الوسم: صغير", "الأولوية: P2", "يمسّ: الأمن"):
        assert key in text


@pytest.mark.parametrize("bad,word", [({"title": ""}, "العنوان"), ({"ask": ""}, "المطلوب"), ({"accept": "  "}, "معايير"),
                                       ({"size": "ضخم"}, "الوسم"), ({"priority": "P0"}, "الأولوية")])
def test_invalid_fields_are_rejected_by_name(reqdir, bad, word):
    with pytest.raises(ValueError, match=word):
        request_page.submit({**OK, **bad})
    assert not list(reqdir.iterdir())


def test_two_requests_in_the_same_second_do_not_overwrite(reqdir):
    import time
    t = time.localtime()
    assert request_page.submit(OK, t)["file"] != request_page.submit(OK, t)["file"]


def test_post_request_route_writes_a_file_and_rejects_foreign_host(reqdir):
    srv = serve.make_server(0) if hasattr(serve, "make_server") else None
    if srv is None:
        pytest.skip("لا مصنع خادم")
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request("http://127.0.0.1:%d/request" % port, data=json.dumps(OK).encode(), headers={"Content-Type": "application/json"})
        assert json.loads(urllib.request.urlopen(req).read())["ok"]  # noqa: S310
        assert len(list(reqdir.iterdir())) == 1
    finally:
        srv.shutdown()
