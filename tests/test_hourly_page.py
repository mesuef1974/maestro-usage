"""اختبار قسم «التوكنات بالساعة»: صفوف الساعة تطابق قاعدة صناعية بأرقام معروفة."""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import hourly_page  # noqa: E402
import ui  # noqa: E402
import usage_db  # noqa: E402


class TestHourlyPage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = usage_db.connect(os.path.join(self.tmp, "u.sqlite3"))
        c = self.con
        c.execute("INSERT INTO sessions(session_key) VALUES ('aaaaaaaa1')")

        def t(i, ts, cc, cr, u=1):
            c.execute("INSERT INTO usage_turns(message_id,session_key,ts,model,input_tokens,cache_creation_tokens,cache_read_tokens,"
                      "output_tokens,thinking_tokens,is_sidechain,source_path,turn_origin) VALUES (?,?,?,?,1,?,?,?,0,0,'p.jsonl','human')",
                      (i, "aaaaaaaa1", ts, "claude-sonnet-5-5", cc, cr, u))
        t("1", "2026-10-20T01:00:00Z", 100, 399_000)
        t("2", "2026-10-20T01:10:00Z", 10, 400_000)
        t("3", "2026-10-20T03:10:00Z", 5000, 400_000)
        c.commit()
        self.data = hourly_page.payload(c)

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def hour(hh):
        return int(datetime.fromisoformat("2026-10-20T%02d:00:00+00:00" % hh).timestamp() // 3600)

    def test_hours_sum_to_db_total(self):
        want = self.con.execute("SELECT SUM(input_tokens+cache_creation_tokens+cache_read_tokens+output_tokens) FROM usage_turns").fetchone()[0]
        self.assertEqual(sum(v for _h, v in self.data["h"]), want)

    def test_one_row_per_active_hour_in_order(self):
        self.assertEqual([h for h, _v in self.data["h"]], [self.hour(1), self.hour(3)])
        self.assertEqual(dict(self.data["h"])[self.hour(1)], (1 + 100 + 399_000 + 1) + (1 + 10 + 400_000 + 1))

    def test_payload_has_numbers_only_and_render_escapes(self):
        for h, v in self.data["h"]:
            self.assertTrue(isinstance(h, int) and isinstance(v, int))
        page = ui.render("hourly", self.data, {"__STAMP__": "الآن"})
        m = re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S)
        self.assertEqual(json.loads(m.group(1))["h"], self.data["h"])
        for token in ("__LIB__", "__DATA__", "__STAMP__"):
            self.assertNotIn(token, page)


if __name__ == "__main__":
    unittest.main()
