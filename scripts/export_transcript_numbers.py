"""يصدّر من سجلّ جلسة Claude Code (jsonl) أرقامًا فقط، سطرًا لكل دور: message_id وts وmodel والحقول الأربعة.
لا يطبع ولا يحفظ أي نصّ من السجلّ. الاستعمال: python export_transcript_numbers.py <سجل.jsonl> <خرج.jsonl>
"""
import json
import sys


def export(src, dst):
    seen, n = set(), 0
    with open(src, encoding="utf-8") as f, open(dst, "w", encoding="utf-8") as out:
        for ln in f:
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            m = d.get("message") or {}
            u = m.get("usage")
            if d.get("type") != "assistant" or not u:
                continue
            mid = m.get("id") or d.get("uuid")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            row = dict(message_id=mid, ts=d["timestamp"], model=m.get("model") or "unknown",
                       input_tokens=int(u.get("input_tokens") or 0), cache_creation_tokens=int(u.get("cache_creation_input_tokens") or 0),
                       cache_read_tokens=int(u.get("cache_read_input_tokens") or 0), output_tokens=int(u.get("output_tokens") or 0))
            out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
    return n


if __name__ == "__main__":
    print(export(sys.argv[1], sys.argv[2]))
