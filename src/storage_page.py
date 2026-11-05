"""صفحة «حجم البيانات»: حمولة آخر مسح من storage_scans/storage_dirs مع ربط المشاريع بالقاعدة، وتاريخ المسوح لمنحنى النمو،
وعمليات الحجر. أرقام ومجلدات وامتدادات فقط."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import storage_scan  # noqa: E402


def _rows(con, ts, kind):
    return [dict(name=n, bytes=b, files=f, newest=nw, oldest=od, b7=a, b30=b30, b90=b90, b90p=b90p, jsonl=j, sub=s)
            for n, b, f, nw, od, a, b30, b90, b90p, j, s in con.execute(
                "SELECT name, bytes, files, newest, oldest, b7, b30, b90, b90p, jsonl, sub FROM storage_dirs WHERE ts=? AND kind=? ORDER BY bytes DESC",
                (ts, kind))]


def payload(con):
    ts = storage_scan.last_scan_ts(con)
    scan = None
    top = proj = ext = []
    if ts:
        tb, files, sec = con.execute("SELECT total_bytes, files, seconds FROM storage_scans WHERE ts=?", (ts,)).fetchone()
        scan = dict(ts=ts, bytes=tb, files=files, seconds=sec)
        top = _rows(con, ts, "top")
        proj = _rows(con, ts, "proj")
        ext = _rows(con, ts, "ext")
        facts = storage_scan.project_facts(con)
        for r in proj:
            f = facts.get(r["name"], {})
            r["exists"] = f.get("exists")
            r["ingested"] = f.get("ingested")
        for r in top:
            r["kind"] = storage_scan.KIND_OF.get(r["name"], "foreign")
    kinds = []
    for k, label, what, why, safe in storage_scan.KINDS:
        rows = [r for r in top if r["kind"] == k]
        kinds.append(dict(k=k, label=label, what=what, why=why, safe=safe, bytes=sum(r["bytes"] for r in rows), files=sum(r["files"] for r in rows),
                          b7=sum(r["b7"] for r in rows), b30=sum(r["b30"] for r in rows), b90=sum(r["b90"] for r in rows), b90p=sum(r["b90p"] for r in rows)))
    history = [dict(ts=t, bytes=b, files=f) for t, b, f in con.execute("SELECT ts, total_bytes, files FROM storage_scans ORDER BY ts")]
    actions = storage_scan.quarantine_rows(con)
    return dict(scan=scan, kinds=kinds, top=top, proj=proj, ext=ext, history=history, actions=actions,
                groups=[dict(k=k, label=label, desc=desc, days=d, options=o) for k, label, desc, d, o in storage_scan.GROUPS],
                root="~/.claude", quarantine="~/.maestro/quarantine", min_age_h=storage_scan.MIN_AGE_SEC // 3600,
                interval_min=storage_scan.SCAN_INTERVAL_SEC // 60)


