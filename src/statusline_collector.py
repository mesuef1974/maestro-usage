"""مجمّع statusLine: يقرأ JSON من stdin ويُلحق سطر أرقام ومعرّفات فقط إلى data\\statusline_spool.jsonl.

قواعد: لا يفشل أبدًا (يبتلع كل خطأ ويسجّله في data\\statusline_errors.log)، لا يكتب SQLite، لا يحفظ نصًّا،
يتحمّل غياب أي حقل، ولا يطبع شيئًا للشريط.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SPOOL = os.path.join(DATA_DIR, "statusline_spool.jsonl")
ERRORS = os.path.join(DATA_DIR, "statusline_errors.log")
MAX_ERROR_LOG = 200_000  # بايت؛ يُقتطع بعدها كي لا ينمو بلا حد


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _get(d, *path):
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _iso(epoch):
    e = _num(epoch)
    if e is None:
        return None
    try:
        return datetime.fromtimestamp(e, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def _sid(v):
    """معرّف الجلسة فقط إن بدا معرّفًا (يمنع تسرّب نص عشوائي)."""
    if isinstance(v, str) and 0 < len(v) <= 100 and all(c.isalnum() or c in "-_.:" for c in v):
        return v
    return None


def extract(data):
    """يحوّل JSON الوارد إلى سجل أرقام. بلا نصوص؛ الغائب None."""
    cu = _get(data, "context_window", "current_usage")
    warm = _get(data, "prompt_cache", "warm")
    return {
        "v": 1,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (int(time.time() * 1000) % 1000),
        "session_key": _sid(data.get("session_id")),
        "context_size": _num(_get(data, "context_window", "context_window_size")),
        "context_used_pct": _num(_get(data, "context_window", "used_percentage")),
        "cu_input_tokens": _num(_get(cu, "input_tokens")),
        "cu_output_tokens": _num(_get(cu, "output_tokens")),
        "cu_cache_creation": _num(_get(cu, "cache_creation_input_tokens")),
        "cu_cache_read": _num(_get(cu, "cache_read_input_tokens")),
        "cache_hit_ratio": _num(_get(data, "prompt_cache", "hit_ratio")),
        "cache_warm": (1 if warm else 0) if isinstance(warm, bool) else None,
        "cost_usd": _num(_get(data, "cost", "total_cost_usd")),
    }


def log_error(exc):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(ERRORS) and os.path.getsize(ERRORS) > MAX_ERROR_LOG:
            os.remove(ERRORS)
        with open(ERRORS, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), type(exc).__name__))
    except Exception:
        pass  # لا شيء يعطّل الجلسة أبدًا


def append_spool(rec, path=None):
    path = path or SPOOL
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(rec, ensure_ascii=True, separators=(",", ":")) + "\n"
    with open(path, "a", encoding="utf-8", newline="\n") as f:  # إلحاق سطر واحد دفعة واحدة
        f.write(line)


def main():
    out = ""
    try:
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", errors="replace"))
        if not isinstance(data, dict):
            raise ValueError("not an object")
        rec = extract(data)
        append_spool(rec)
    except Exception as exc:  # noqa: BLE001 — لا يفشل أبدًا
        log_error(exc)
    try:
        sys.stdout.write(out)
        sys.stdout.flush()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
