"""اختبار التعبئة الرجعية لتقسيم كتابة الكاش (ساعة/خمس دقائق)."""
import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import backfill_cc_ttl as bf  # noqa: E402
from test_ingest import Base, a_line, write  # noqa: E402


def with_ttl(mid, ts, h1, m5):
    d = json.loads(a_line(mid, ts, cc=h1 + m5))
    d["message"]["usage"]["cache_creation"] = {"ephemeral_1h_input_tokens": h1, "ephemeral_5m_input_tokens": m5}
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


class TestBackfill(Base):
    def test_fills_only_empty_rows_and_is_idempotent(self):
        p = os.path.join(self.root, "proj", "aaa.jsonl")
        write(p, [a_line("m1", "2026-10-01T00:00:01Z", cc=300), a_line("m2", "2026-10-01T00:00:02Z", cc=50)])
        self.run_ingest()
        write(p, [with_ttl("m1", "2026-10-01T00:00:01Z", 200, 100), a_line("m2", "2026-10-01T00:00:02Z", cc=50)])
        self.assertEqual(bf.run(self.con, self.root, 0), (1, 1, 1))
        got = {r[0]: (r[1], r[2]) for r in self.q("SELECT message_id, cc_1h, cc_5m FROM usage_turns")}
        self.assertEqual(got, {"m1": (200, 100), "m2": (None, None)})
        self.assertEqual(bf.run(self.con, self.root, 0)[2], 0)

    def test_since_skips_old_files(self):
        p = os.path.join(self.root, "proj", "old.jsonl")
        write(p, [with_ttl("m1", "2026-10-01T00:00:01Z", 1, 2)])
        os.utime(p, (1000, 1000))
        self.assertEqual(bf.run(self.con, self.root, time.time() - 3600)[0], 0)


if __name__ == "__main__":
    unittest.main()
