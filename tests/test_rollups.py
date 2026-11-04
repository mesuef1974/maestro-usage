"""اختبارات تجميعات الاستهلاك واستيراد الجلسات الخارجية، على بيانات صناعية."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import import_external  # noqa: E402
import rollups  # noqa: E402
import usage_db  # noqa: E402


def turn(con, mid, ts, model="m-a", sess="s1", i=1, cc=10, cr=100, o=5):
    con.execute("INSERT OR IGNORE INTO sessions(session_key) VALUES (?)", (sess,))
    con.execute("INSERT INTO usage_turns(message_id, session_key, ts, model, input_tokens, cache_creation_tokens, cache_read_tokens, "
                "output_tokens, source_path) VALUES (?,?,?,?,?,?,?,?,?)", (mid, sess, ts, model, i, cc, cr, o, "p"))


@pytest.fixture()
def con(tmp_path):
    c = usage_db.connect(tmp_path / "u.sqlite3")
    # الاثنين 2026-11-02 والأحد 2026-11-01 (أسبوع سابق) وأكتوبر
    turn(c, "a", "2026-11-02T10:00:00Z")
    turn(c, "b", "2026-11-04T10:00:00Z", model="m-b", sess="s2")
    turn(c, "c", "2026-11-01T23:59:00Z")
    turn(c, "d", "2026-10-15T00:00:00Z")
    c.commit()
    return c


def test_week_starts_monday_and_sunday_belongs_to_previous_week(con):
    rollups.refresh(con)
    weeks = {r[0] for r in con.execute("SELECT period_start FROM usage_rollups WHERE grain='week'")}
    assert weeks == {"2026-11-02", "2026-10-26", "2026-10-12"}


def test_rollup_totals_equal_raw_totals_at_every_grain(con):
    rollups.refresh(con)
    raw = con.execute("SELECT COUNT(*), SUM(input_tokens), SUM(cache_read_tokens), SUM(output_tokens) FROM usage_turns").fetchone()
    for g in ("day", "week", "month"):
        got = con.execute("SELECT SUM(turns), SUM(input_tokens), SUM(cache_read_tokens), SUM(output_tokens) FROM usage_rollups WHERE grain=?", (g,)).fetchone()
        assert got == raw, g


def test_refresh_is_idempotent(con):
    n1 = rollups.refresh(con)
    snap = con.execute("SELECT grain, period_start, model, turns FROM v_usage_rollups ORDER BY 1,2,3").fetchall()
    assert rollups.refresh(con) == n1
    assert con.execute("SELECT grain, period_start, model, turns FROM v_usage_rollups ORDER BY 1,2,3").fetchall() == snap


def test_payload_models_and_last_session(con):
    p = rollups.payload(con)
    assert p["week_start"] == "2026-11-02" and p["month_start"] == "2026-11-01"
    assert {m["model"] for m in p["week_models"]} == {"m-a", "m-b"}
    assert p["session"]["key"] == "s2" and p["session"]["models"][0]["model"] == "m-b"
    assert p["monthly"][0]["sessions"] == 2 and p["weekly"][0]["period"] == "2026-11-02"


def test_import_external_is_idempotent_and_rejects_bad_rows(con, tmp_path):
    f = tmp_path / "x.jsonl"
    good = dict(message_id="msg_1", ts="2026-11-04T16:00:00.000Z", model="claude-x", input_tokens=1, cache_creation_tokens=2,
                cache_read_tokens=3, output_tokens=4)
    f.write_text("\n".join([json.dumps(good), json.dumps({**good, "message_id": "msg_2", "model": "نص عربي"}), "not json"]), encoding="utf-8")
    assert import_external.import_file(con, f, "cloud-1") == (1, 0, 2)
    assert import_external.import_file(con, f, "cloud-1") == (0, 1, 2)
    assert con.execute("SELECT COUNT(*) FROM usage_turns WHERE session_key='cloud-1'").fetchone()[0] == 1
    assert con.execute("SELECT source_path FROM usage_turns WHERE message_id='msg_1'").fetchone()[0] == "external:cloud"


def test_import_external_rejects_bad_session_key(con, tmp_path):
    f = tmp_path / "x.jsonl"
    f.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        import_external.import_file(con, f, "مفتاح عربي")


def test_run_dir_imports_once_and_again_after_change(con, tmp_path):
    d = tmp_path / "ext"
    d.mkdir()
    row = dict(message_id="m1", ts="2026-11-04T16:00:00.000Z", model="x", input_tokens=1, cache_creation_tokens=0, cache_read_tokens=0, output_tokens=1)
    f = d / "cloud-9.jsonl"
    f.write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert import_external.run_dir(con, str(d)) == 1
    assert import_external.run_dir(con, str(d)) == 0  # البصمة لم تتغيّر
    f.write_text(json.dumps(row) + "\n" + json.dumps({**row, "message_id": "m2"}) + "\n", encoding="utf-8")
    assert import_external.run_dir(con, str(d)) == 1
    assert con.execute("SELECT COUNT(*) FROM usage_turns WHERE session_key='cloud-9'").fetchone()[0] == 2


def test_models_dimension_is_normalized_and_rollups_use_ids(con):
    rollups.refresh(con)
    names = dict(con.execute("SELECT name, family FROM models").fetchall())
    assert set(names) == {"m-a", "m-b"} and names["m-a"] is None
    assert "model" not in [r[1] for r in con.execute("PRAGMA table_info(usage_rollups)")]
    assert con.execute("SELECT COUNT(*) FROM usage_rollups WHERE model_id NOT IN (SELECT model_id FROM models)").fetchone()[0] == 0
    assert rollups.family("claude-opus-5-5") == "opus" and rollups.family("x") is None


def test_old_text_model_rollups_table_is_migrated(tmp_path):
    import sqlite3
    path = tmp_path / "old.sqlite3"
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE usage_rollups (grain TEXT, period_start TEXT, model TEXT, turns INTEGER)")
    c.commit(); c.close()
    c = usage_db.connect(path)
    assert "model_id" in [r[1] for r in c.execute("PRAGMA table_info(usage_rollups)")]
