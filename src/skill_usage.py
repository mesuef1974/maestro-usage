"""يحصي استدعاءات المهارات (أداة Skill) والأوامر المائلة من سجلات الجلسات ويحفظها في data/skill_usage.json.

قراءة فقط، صفر توكنات، ولا يُخزَّن إلا اسم المهارة وعدد الاستدعاءات وعدد الجلسات وأول/آخر يوم. المسح كامل (دقائق على عشرة جيجابايت)،
فيُشغَّل يدويًّا أو من مهمة مجدولة ولا يدخل في دورة الدقيقة؛ صفحة المهارات تقرأ آخر نتيجة محفوظة.
"""
import collections
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.join(os.path.expanduser("~"), ".claude", "projects")
DEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "skill_usage.json")
CMD = re.compile(r"<command-name>/?([^<\s]+)</command-name>")


def _content(o):
    c = (o.get("message") or {}).get("content")
    return c if isinstance(c, list) else []


def scan(root=ROOT):
    by = collections.defaultdict(lambda: dict(n=0, sessions=set(), first=None, last=None, via=collections.Counter()))
    files = 0

    def note(name, sess, ts, via):
        d = by[name]
        d["n"] += 1
        d["sessions"].add(sess)
        d["via"][via] += 1
        if ts:
            d["first"] = min(d["first"] or ts, ts)
            d["last"] = max(d["last"] or ts, ts)

    for dp, _dn, fn in os.walk(root):
        for f in fn:
            if not f.endswith(".jsonl"):
                continue
            files += 1
            try:
                with open(os.path.join(dp, f), encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        is_tool = '"name":"Skill"' in line
                        if not is_tool and not ("<command-name>" in line and '"type":"user"' in line):
                            continue
                        try:
                            o = json.loads(line)
                        except ValueError:
                            continue
                        day = (o.get("timestamp") or "")[:10]
                        if is_tool:
                            for c in _content(o):
                                if c.get("type") == "tool_use" and c.get("name") == "Skill" and (c.get("input") or {}).get("skill"):
                                    note(c["input"]["skill"], f[:-6], day, "tool")
                        else:
                            m = CMD.search(json.dumps(o.get("message") or {}, ensure_ascii=False))
                            if m:
                                note(m.group(1).lstrip("/"), f[:-6], day, "slash")
            except OSError:
                pass
    usage = {k: dict(n=v["n"], sessions=len(v["sessions"]), first=v["first"], last=v["last"], via=dict(v["via"])) for k, v in by.items()}
    return dict(files=files, scanned_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), usage=usage)


def load(path=DEST):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return dict(files=0, scanned_at=None, usage={})


def main(argv=None):
    res = scan()
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    tmp = DEST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DEST)
    print("files %d names %d" % (res["files"], len(res["usage"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
