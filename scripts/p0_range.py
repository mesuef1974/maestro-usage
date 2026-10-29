"""استقصاء المدى: يمرّ على كل السجلات ويجمع أرقامًا فقط (بلا نصوص). مخرجه JSON ملخّص."""
import json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(__file__))
import p0_survey as s

TITLE_RE = re.compile(r"^\s*(\d{4})\b")
def main():
    glob_ids = {}; cross_dup = 0
    per_day = collections.defaultdict(lambda: [0,0,0,0,0])  # turns,in,cc,cr,out
    per_model = collections.defaultdict(lambda: [0,0,0,0,0])
    tot = [0]*5
    kinds = collections.Counter(); sess_main = set(); sess_all = set()
    first = last = None; file_mtimes = []
    sid_mismatch = 0; sub_files = 0; titles_num = 0; titles_any = 0; sess_with_title = set()
    title_numbers = collections.defaultdict(set)  # session -> set of leading 4-digit numbers
    n_files = 0; bad = 0
    for p in s.files():
        n_files += 1
        kind, _ = s.classify(p); kinds[kind] += 1
        base = os.path.basename(p)[:-6]
        file_mtimes.append(os.path.getmtime(p))
        best = {}
        sid_seen = set()
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"type":"assistant"' in line or '"type":"custom-title"' in line:
                    try: o = json.loads(line)
                    except Exception: bad += 1; continue
                    if o.get("type") == "custom-title":
                        titles_any += 1; t = o.get("customTitle") or ""
                        m = TITLE_RE.match(t)
                        if m: title_numbers[o.get("sessionId")].add(m.group(1))
                        sess_with_title.add(o.get("sessionId")); continue
                    if o.get("type") != "assistant": continue
                    sid = o.get("sessionId"); sid_seen.add(sid)
                    m = o.get("message") or {}; u = m.get("usage") or {}
                    mid = m.get("id")
                    if not mid: continue
                    rec = (u.get("output_tokens") or 0, u.get("input_tokens") or 0, u.get("cache_creation_input_tokens") or 0, u.get("cache_read_input_tokens") or 0, m.get("model"), (o.get("timestamp") or "")[:10], o.get("timestamp"))
                    if mid not in best or rec[0] >= best[mid][0]: best[mid] = rec
        for sid in sid_seen:
            sess_all.add(sid)
            if kind == "main":
                sess_main.add(sid)
                if sid != base: sid_mismatch += 1
        if kind == "subagent": sub_files += 1
        for mid, (out, i, cc, cr, model, day, ts) in best.items():
            if mid in glob_ids: cross_dup += 1; continue
            glob_ids[mid] = 1
            for d in (per_day[day], per_model[model]):
                d[0]+=1; d[1]+=i; d[2]+=cc; d[3]+=cr; d[4]+=out
            tot[0]+=1; tot[1]+=i; tot[2]+=cc; tot[3]+=cr; tot[4]+=out
            if ts:
                if first is None or ts < first: first = ts
                if last is None or ts > last: last = ts
    res = dict(files=n_files, kinds=dict(kinds), unique_turns=tot[0], cross_file_dup_ids=cross_dup, bad_lines=bad,
        totals=dict(input=tot[1], cache_creation=tot[2], cache_read=tot[3], output=tot[4]),
        first_ts=first, last_ts=last, sessions_main=len(sess_main), sessions_any=len(sess_all), main_sid_ne_filename=sid_mismatch,
        sessions_with_title=len(sess_with_title), sessions_with_4digit_title=len(title_numbers),
        oldest_file_mtime=min(file_mtimes), newest_file_mtime=max(file_mtimes),
        per_model={k or "<none>": dict(zip(("turns","in","cc","cr","out"), v)) for k, v in per_model.items()},
        per_day={k: dict(zip(("turns","in","cc","cr","out"), v)) for k, v in sorted(per_day.items())})
    json.dump(res, open(r"C:/Users/mesue/maestro_usage/data/p0_range.json", "w"), indent=1)
    json.dump({k: sorted(v) for k, v in title_numbers.items()}, open(r"C:/Users/mesue/maestro_usage/data/p0_title_numbers.json","w"))
    print("done", tot[0], first, last)
main()
