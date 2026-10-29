"""أين تتكرر message.id عبر الملفات؟ أرقام فقط."""
import json, os, sys, collections
sys.path.insert(0, os.path.dirname(__file__))
import p0_survey as s
first = {}; pairs = collections.Counter(); same_vals = diff_vals = 0; sid_diff = 0
for p in sorted(s.files()):
    kind = s.classify(p)[0]; base = os.path.basename(p)[:-6]; seen = set()
    for line in open(p, encoding="utf-8", errors="replace"):
        if '"type":"assistant"' not in line: continue
        o = json.loads(line); m = o.get("message") or {}; mid = m.get("id")
        if not mid or mid in seen: continue
        seen.add(mid); u = m.get("usage") or {}
        val = (u.get("cache_read_input_tokens"), u.get("input_tokens"), u.get("cache_creation_input_tokens"))
        if mid in first:
            k0, v0, sid0 = first[mid]
            pairs[(k0, kind)] += 1
            if v0 == val: same_vals += 1
            else: diff_vals += 1
            if sid0 != o.get("sessionId"): sid_diff += 1
        else: first[mid] = (kind, val, o.get("sessionId"))
print(dict(pairs), "same_usage", same_vals, "diff_usage", diff_vals, "different_sessionId", sid_diff)
