"""تحليل الأسناد عند تعادل first_ts: هل sessionId داخل السطر يحسم؟ أرقام فقط."""
import json, os, sys, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import usage_ingest as ui
ROOT = ui.PROJECTS
cand = {}  # mid -> {rel: sessionId_in_line}
keys = {}
for p in ui.iter_logs(ROOT):
    rel = os.path.relpath(p, ROOT); keys[rel] = ui.owner_key(ROOT, p)
    for line in open(p, encoding="utf-8", errors="replace"):
        if '"type":"assistant"' in line:
            try: o = json.loads(line)
            except ValueError: continue
            m = o.get("message") or {}
            if m.get("id") and m.get("model") != "<synthetic>":
                cand.setdefault(m["id"], {})[rel] = o.get("sessionId")
c = collections.Counter()
for mid, d in cand.items():
    if len(d) < 2: continue
    matches = [r for r, sid in d.items() if keys[r] == sid]
    sids = set(d.values())
    c["groups"] += 1
    c["one_sessionId_all_copies" if len(sids) == 1 else "mixed_sessionIds"] += 1
    c["exactly_one_file_key_matches_line_sessionId" if len(matches) == 1 else ("zero_match" if not matches else "multi_match")] += 1
    mains = [r for r in d if "subagents" not in r]
    c["has_main_and_sub" if mains and len(mains) < len(d) else ("all_main" if mains else "all_sub")] += 1
print(dict(c))

import sqlite3, usage_db
con = usage_db.connect()
own = dict(con.execute("SELECT message_id, session_key FROM usage_turns"))
v = collections.Counter(); ex = []
for mid, d in cand.items():
    if len(d) < 2 or mid not in own: continue
    sids = set(d.values())
    if len(sids) == 1:
        sid = next(iter(sids))
        v["owner_key_matches_line_sessionId" if own[mid] == sid else "owner_key_DIFFERS"] += 1
        if own[mid] != sid and len(ex) < 3: ex.append((mid[:12], len(d)))
    else:
        v["mixed_sessionIds_owner_in_set" if own[mid] in sids else "mixed_owner_outside"] += 1
print(dict(v), ex)
