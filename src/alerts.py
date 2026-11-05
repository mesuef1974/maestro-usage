"""تنبيه خارج الصفحة: إشعار ويندوز حين يتوقّع النموذج بلوغ 100% من الحصة قبل تصفيرها.

يعمل داخل الدورة المجدولة بعد البناء. القاعدة: لكل نافذة (الأسبوعي، Fable) إشعار واحد لكل زمن تصفير (لا يتكرر كل دقيقة)،
ويُعاد إن تغيّر زمن التصفير أو عاد التوقّع إلى «يبلغ 100%» بعد أن زال. الحالة في data/alerts_state.json.
الإشعار عبر PowerShell (BurntToast غير مطلوب): نافذة MessageBox غير معطِّلة تُفتح في عملية منفصلة؛ فشلها لا يوقف الدورة.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
STATE = os.path.join(DATA, "alerts_state.json")
NAMES = {"week": "الحصة الأسبوعية لكل النماذج", "fable": "حصة Fable الأسبوعية"}
PS_TOAST = (
    "Add-Type -AssemblyName System.Windows.Forms; "
    "$n = New-Object System.Windows.Forms.NotifyIcon; $n.Icon = [System.Drawing.SystemIcons]::Warning; $n.Visible = $true; "
    "$n.ShowBalloonTip(15000, $env:MZ_TITLE, $env:MZ_BODY, [System.Windows.Forms.ToolTipIcon]::Warning); Start-Sleep -Seconds 16; $n.Dispose()"
)


def _clock(iso):
    try:
        d = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone()
        return d.strftime("%a %H:%M")
    except (TypeError, ValueError):
        return str(iso)


def due(quota, state):
    """يعيد قائمة (اسم النافذة، مفتاح الحالة، نص) لما يستحق إشعارًا الآن وفق quota (حمولة quota_model) والحالة السابقة."""
    out = []
    for name, q in (quota or {}).items():
        fc = (q or {}).get("fc") or {}
        key = "%s@%s" % (name, fc.get("resets") or "")
        full = fc.get("full_at")
        if not full:
            if state.get(name) == key:
                state[name] = key + "#cleared"  # زال التوقّع: الإشعار التالي لنفس التصفير مسموح
            continue
        if state.get(name) == key:
            continue
        out.append((name, key, "%s: بمعدل الحرق الحالي تبلغ 100%% نحو %s، والتصفير %s. التوقّع عند التصفير %d%%." % (
            NAMES.get(name, name), _clock(full), _clock(fc.get("resets")), min(999, round(fc.get("at_reset") or 0)))))
    return out


def load_state(path=STATE):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state, path=STATE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, path)


def notify(title, body):
    """إشعار ويندوز في عملية منفصلة لا تنتظرها الدورة؛ خارج ويندوز لا شيء."""
    if sys.platform != "win32":
        return False
    env = dict(os.environ, MZ_TITLE=title, MZ_BODY=body)
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", PS_TOAST], env=env,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
    return True


def run(quota, path=STATE, send=notify):
    """يحسب المستحق ويرسله ويحدّث الحالة؛ يعيد عدد الإشعارات المرسلة."""
    state = load_state(path)
    items = due(quota, state)
    sent = 0
    for name, key, text in items:
        try:
            if send("ميزان: تحذير الحصة", text):
                sent += 1
        except OSError:
            continue
        state[name] = key
    save_state(state, path)
    return sent


if __name__ == "__main__":  # تجربة يدوية: python src\alerts.py --test يعرض إشعارًا واحدًا
    if "--test" in sys.argv[1:]:
        print("sent" if notify("ميزان: تجربة التنبيه", "هذا إشعار تجريبي من دورة ميزان؛ لا يعني شيئًا عن الحصة.") else "not windows")
