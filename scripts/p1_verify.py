"""تحقق المرحلة 1 على القاعدة الحقيقية. أرقام فقط."""
import json, os, sqlite3, sys, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import usage_db
ROOT = os.path.join(os.path.expanduser("~"), ".claude", "projects")
con = usage_db.connect()
q = lambda s, *a: con.execute(s, a).fetchall()

t = q("SELECT COUNT(*),SUM(input_tokens),SUM(cache_creation_tokens),SUM(cache_read_tokens),SUM(output_tokens) FROM usage_turns")[0]
tot = sum(t[1:])
print("rows", t[0], "input", t[1], "cc", t[2], "cr", t[3], "out", t[4], "total_B", round(tot/1e9, 3), "cr_share", round(t[3]/tot, 4))
print("sessions", q("SELECT COUNT(*) FROM sessions")[0][0], "with_turns", q("SELECT COUNT(DISTINCT session_key) FROM usage_turns")[0][0])
print("numbered", q("SELECT number_source, COUNT(*) FROM sessions GROUP BY 1"))
for m, n, s in q("SELECT model, COUNT(*), SUM(input_tokens+cache_creation_tokens+cache_read_tokens+output_tokens) FROM usage_turns GROUP BY 1 ORDER BY 3 DESC"):
    print(" ", m, n, round(100*s/tot, 1))

# 1) تكرار: سجل 0101 الحقيقي
key = "99553e2f-5356-49f2-aed0-1648322c6b41"
path = [os.path.join(dp, key + ".jsonl") for dp, dn, fn in os.walk(ROOT) if key + ".jsonl" in fn][0]
ids = set(); sid_lines = 0
for line in open(path, encoding="utf-8", errors="replace"):
    if '"type":"assistant"' in line:
        o = json.loads(line); m = o["message"]
        if m.get("model") != "<synthetic>" and m.get("id"): ids.add(m["id"])
rel = os.path.relpath(path, ROOT)
own = q("SELECT COUNT(*) FROM usage_turns WHERE source_path=?", rel)[0][0]
mine_in_ids = 0
for i in range(0, len(ids), 500):
    ch = list(ids)[i:i+500]
    mine_in_ids += q("SELECT COUNT(*) FROM usage_turns WHERE message_id IN (%s)" % ",".join("?"*len(ch)), *ch)[0][0]
print("0101: unique ids in log", len(ids), "found in db", mine_in_ids, "owned by this file", own, "session rows", q("SELECT COUNT(*) FROM usage_turns WHERE session_key=?", key)[0][0])

# 2) اختبار قاعدة الإسناد على الحالات الحقيقية: المالك = أقدم first_ts؛ ابحث عن مخالفات
viol = q("""SELECT COUNT(*) FROM usage_turns t JOIN ingest_state o ON o.source_path=t.source_path
            WHERE EXISTS (SELECT 1 FROM ingest_state s WHERE s.first_ts < o.first_ts AND s.session_key=t.session_key AND 0)""")
# مقارنة مباشرة: لكل رد مكرّر أعد حساب المالك من الملفات (مسح مستقل)
first = {}
for r in q("SELECT source_path, first_ts FROM ingest_state"): first[r[0]] = r[1] or ""
seen = {}  # mid -> set(rel)
for dp, dn, fn in os.walk(ROOT):
    for f in fn:
        if not f.endswith(".jsonl"): continue
        p = os.path.join(dp, f); rel = os.path.relpath(p, ROOT)
        for line in open(p, encoding="utf-8", errors="replace"):
            if '"type":"assistant"' in line:
                try: m = json.loads(line)["message"]
                except ValueError: continue
                if m.get("id") and m.get("model") != "<synthetic>": seen.setdefault(m["id"], set()).add(rel)
dups = {k: v for k, v in seen.items() if len(v) > 1}
owner = dict(q("SELECT message_id, source_path FROM usage_turns"))
bad = sum(1 for k, v in dups.items() if owner.get(k) != min(v, key=lambda r: (first.get(r, ""), r)))
tie = sum(1 for k, v in dups.items() if len({first.get(r, "") for r in v}) < len(v))
print("dup ids", len(dups), "owner != oldest-first_ts", bad, "ties on first_ts", tie, "unique ids in logs", len(seen), "rows", t[0])
# هل مالك الرد المكرّر هو الجلسة التي يحمل سطره sessionId لها؟ (فحص عيّنة من الملفات المالكة)
cnt = collections.Counter()
for k, v in list(dups.items()):
    o = owner.get(k)
    cnt["owner_is_main" if "subagents" not in (o or "") else "owner_is_subagent"] += 1
print(dict(cnt))
