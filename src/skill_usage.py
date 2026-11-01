"""يحصي استدعاءات المهارات (أداة Skill) والأوامر المائلة من سجلات الجلسات ويحفظها في data/skill_usage.json.

قراءة فقط، صفر توكنات، ولا يُخزَّن إلا اسم المهارة وعدد الاستدعاءات وعدد الجلسات وأول/آخر يوم. المسح كامل (دقائق على عشرة جيجابايت)،
فيُشغَّل يدويًّا أو من مهمة مجدولة ولا يدخل في دورة الدقيقة؛ صفحة المهارات تقرأ آخر نتيجة محفوظة.

التفريد: الجلسات المستأنفة والمتفرّعة تنسخ التاريخ، فيُعدّ استدعاء الأداة بمعرّف كتلة tool_use (id) مرة واحدة عبر كل الملفات،
والأمر المائل بمعرّف الرسالة (uuid السطر أو message.id) مرة واحدة كذلك؛ السطر بلا معرّف يُعدّ بموضعه في ملفه. مفتاح الجلسة
للوكيل الفرعي هو مجلد المالك (usage_ingest.owner_key) فيُحسب استدعاؤه ضمن الجلسة نفسها.
"""
import collections
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usage_ingest import owner_key  # noqa: E402

ROOT = os.path.join(os.path.expanduser("~"), ".claude", "projects")
DEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "skill_usage.json")
CMD = re.compile(r"<command-name>/?([^<\s]+)</command-name>")


def _content(o):
    c = (o.get("message") or {}).get("content")
    return c if isinstance(c, list) else []


def _msg_id(o):
    """معرّف الرسالة: uuid السطر ثم message.id؛ None إن غابا."""
    return o.get("uuid") or (o.get("message") or {}).get("id") or None


def scan(root=ROOT):
    by = collections.defaultdict(lambda: dict(n=0, sessions=set(), first=None, last=None, via=collections.Counter()))
    files = 0
    seen = set()  # معرّفات tool_use والرسائل التي عُدَّت؛ النسخ المكرّرة في ملفات أخرى تُتجاهل

    def note(name, sess, ts, via, ident):
        if ident in seen:
            return
        seen.add(ident)
        d = by[name]
        d["n"] += 1
        d["sessions"].add(sess)
        d["via"][via] += 1
        if ts:
            d["first"] = min(d["first"] or ts, ts)
            d["last"] = max(d["last"] or ts, ts)

    for dp, dn, fn in os.walk(root):
        dn.sort()  # ترتيب ثابت: الأصل (اسم الجلسة) يسبق مجلد subagents الفرعي والنسخ
        for f in sorted(fn):
            if not f.endswith(".jsonl"):
                continue
            files += 1
            path = os.path.join(dp, f)
            sess = owner_key(root, path)
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh):
                        is_tool = '"name":"Skill"' in line
                        if not is_tool and not ("<command-name>" in line and '"type":"user"' in line):
                            continue
                        try:
                            o = json.loads(line)
                        except ValueError:
                            continue
                        day = (o.get("timestamp") or "")[:10]
                        if is_tool:
                            for j, c in enumerate(_content(o)):
                                if c.get("type") == "tool_use" and c.get("name") == "Skill" and (c.get("input") or {}).get("skill"):
                                    ident = ("tool", c.get("id")) if c.get("id") else ("line", path, i, j)
                                    note(c["input"]["skill"], sess, day, "tool", ident)
                        else:
                            m = CMD.search(json.dumps(o.get("message") or {}, ensure_ascii=False))
                            if m:
                                mid = _msg_id(o)
                                ident = ("msg", mid) if mid else ("line", path, i, 0)
                                note(m.group(1).lstrip("/"), sess, day, "slash", ident)
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
