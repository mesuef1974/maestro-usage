"""مقارنة cost-state (اختبار فقط، لا يُحفظ) مع القاعدة لعيّنة جلسات. أرقام فقط."""
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import usage_db
import usage_ingest as ui
con = usage_db.connect(); R = ui.PROJECTS
rows = []; fields = None
for p in ui.iter_logs(R):
    if "subagents" in p: continue
    last = None
    for line in open(p, encoding="utf-8", errors="replace"):
        if '"type":"cost-state"' in line: last = line
    if not last: continue
    o = json.loads(last); mu = o.get("modelUsage") or {}
    if fields is None and mu: fields = sorted(next(iter(mu.values())).keys())
    key = ui.owner_key(R, p)
    agg = {"in": 0, "cc": 0, "cr": 0, "out": 0}
    for v in mu.values():
        agg["in"] += v.get("inputTokens", 0); agg["cc"] += v.get("cacheCreationInputTokens", 0)
        agg["cr"] += v.get("cacheReadInputTokens", 0); agg["out"] += v.get("outputTokens", 0)
    db = con.execute("SELECT SUM(input_tokens),SUM(cache_creation_tokens),SUM(cache_read_tokens),SUM(output_tokens) FROM usage_turns WHERE session_key=?", (key,)).fetchone()
    if db[0] is None: continue
    rows.append((agg, db, os.path.getsize(p)))
print("modelUsage fields", fields)
print("sessions compared", len(rows))
rat = lambda a, b: (a / b) if b else None
cr = [rat(d[2], a["cr"]) for a, d, _ in rows if a["cr"] > 1e6]
cr.sort()
n = len(cr)
print("cache_read db/cost_state: n", n, "median", round(cr[n//2], 3), "p10", round(cr[n//10], 3), "p90", round(cr[9*n//10], 3), "within±2%", sum(1 for x in cr if abs(x-1) <= .02))
sa = sum(a["cr"] for a, _, _ in rows); sd = sum(d[2] for _, d, _ in rows)
print("sum cr cost_state", sa, "db", sd, "ratio", round(sd/sa, 3))
