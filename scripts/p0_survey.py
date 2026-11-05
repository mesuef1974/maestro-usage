"""استقصاء المرحلة 0: بنية سجلات jsonl. يُخرج أعدادًا وأسماء حقول فقط، بلا أي قيمة نصية."""
import json
import os
import sys
import collections

ROOT = r"C:\Users\mesue\.claude\projects"

def files():
    out = []
    for dp, dn, fn in os.walk(ROOT):
        for f in fn:
            if f.endswith(".jsonl"):
                out.append(os.path.join(dp, f))
    return out

def classify(p):
    rel = os.path.relpath(p, ROOT).split(os.sep)
    return "subagent" if "subagents" in rel else "main", len(rel)

def keys_of(o, prefix="", depth=0, acc=None):
    if acc is None: acc = set()
    if isinstance(o, dict):
        for k, v in o.items():
            acc.add(prefix + k)
            if depth < 2 and isinstance(v, dict): keys_of(v, prefix + k + ".", depth + 1, acc)
    return acc

def structure(p):
    types = collections.Counter(); fields = collections.defaultdict(set)
    ids = collections.defaultdict(list)  # message.id -> list of (output_tokens, cache_read, input, cc)
    for line in open(p, encoding="utf-8", errors="replace"):
        try: o = json.loads(line)
        except Exception: types["<bad>"] += 1; continue
        t = o.get("type", "<none>"); types[t] += 1
        fields[t] |= {k for k in o.keys()}
        if t == "assistant":
            m = o.get("message") or {}
            u = m.get("usage") or {}
            fields["assistant.message"] |= set(m.keys())
            fields["assistant.usage"] |= set(u.keys())
            if isinstance(u.get("output_tokens_details"), dict): fields["assistant.usage.otd"] |= set(u["output_tokens_details"].keys())
            ids[m.get("id")].append((u.get("output_tokens"), u.get("cache_read_input_tokens"), u.get("input_tokens"), u.get("cache_creation_input_tokens"), bool(o.get("isSidechain")), o.get("requestId") is not None))
        if t not in ("assistant", "user"):
            fields[t+".sub"] |= {k for k in o.keys()}
    return types, fields, ids

if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "inventory":
        fs = files(); kinds = collections.Counter(); sz = 0
        for p in fs:
            k, depth = classify(p); kinds[(k, depth)] += 1; sz += os.path.getsize(p)
        print("files", len(fs), "MB", round(sz/1e6,1)); print(dict(kinds))
    elif mode == "struct":
        p = sys.argv[2]; types, fields, ids = structure(p)
        print("size_MB", round(os.path.getsize(p)/1e6,2), classify(p))
        print("types", dict(types))
        for k, v in fields.items(): print(k, sorted(v))
        n = len(ids); dup = sum(1 for v in ids.values() if len(v) > 1)
        lines = sum(len(v) for v in ids.values())
        print("assistant lines", lines, "unique ids", n, "ids with dups", dup)
        # which duplicate carries max output; is usage cumulative?
        last_is_max = first_is_max = mono = const_other = 0
        for i, v in ids.items():
            if len(v) < 2: continue
            outs = [x[0] or 0 for x in v]
            if outs[-1] == max(outs): last_is_max += 1
            if outs[0] == max(outs): first_is_max += 1
            if all(outs[j] <= outs[j+1] for j in range(len(outs)-1)): mono += 1
            if len({(x[1], x[2], x[3]) for x in v}) == 1: const_other += 1
        print("dups:", dup, "last_is_max", last_is_max, "first_is_max", first_is_max, "monotonic_out", mono, "input/cache_constant", const_other)
