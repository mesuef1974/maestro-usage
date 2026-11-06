"""سجلّ صفحات المنصة: مصدر وحيد للتنقّل والعناوين والأقسام التي تُبقيها كل صفحة من قالبها.
القالب الواحد يخدم عدّة صفحات: `ui.render` يحذف من القالب كل قسم لا يرد في `sections` الصفحة."""

# أيقونات الشريط الجانبي (مسارات داخل svg 24x24، خطّ لا تعبئة)
ICON = {
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "home": '<path d="M3 11l9-8 9 8M5 10v10h14V10"/>',
    "gauge": '<path d="M4 16a8 8 0 1 1 16 0M12 16l4-5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "wave": '<path d="M3 12h3l2-6 4 12 3-9 2 3h4"/>',
    "layers": '<path d="M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5"/>',
    "pie": '<path d="M12 3v9h9a9 9 0 1 1-9-9z"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "users": '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M17 11a3 3 0 1 0 0-6M21 20c0-2.5-1.6-4.6-4-5.5"/>',
    "bars": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "split": '<path d="M12 3v6M12 9L6 15v6M12 9l6 6v6"/>',
    "zap": '<path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z"/>',
    "power": '<path d="M12 3v9M6.3 6.3a8 8 0 1 0 11.4 0"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "db": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "disk": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 14h18M7 17h.01M7 8h.01"/>',
    "pulse": '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
    "flow": '<rect x="15" y="3" width="6" height="5" rx="1"/><rect x="3" y="10" width="6" height="5" rx="1"/><rect x="15" y="16" width="6" height="5" rx="1"/><path d="M15 5.5h-3v7h3M15 18.5h-3v-6H9"/>',
}

# أقسام الصفحة الواحدة بالترتيب: (المعرّف، العنوان، الأيقونة). الشريط الجانبي وعناوين المجموعات يقرآن من هنا وحده.
SECTIONS = [
    ("quota", "الحصة الأسبوعية", "gauge"),
    ("usage", "الاستهلاك", "layers"),
    ("skills", "المهارات", "grid"),
    ("data", "البيانات والتخزين", "db"),
    ("auto", "الأتمتة", "flow"),
]
SECTION_TITLE = {sid: title for sid, title, _ in SECTIONS}

# أجزاء الصفحة الواحدة بالترتيب: (المعرّف، القالب، الأقسام). يخدم كل قالب جزءًا واحدًا (نسخة JS واحدة) إلا «static» فهو HTML بلا نص برمجي.
# الاسم الذي يبدأ بـ@ يولّد عنوان قسم من SECTIONS قبل ما يليه.
_ROWS = [
    ("main", "dashboard.html", ["@quota", "limits", "h3", "@usage", "filters", "tiles", "month", "h1", "h2"]),
    ("hourly", "hourly.html", ["ht"]),
    ("summary", "summary.html", ["sum"]),
    ("skills", "skills.html", ["@skills", "tiles", "filters2", "tbl", "gone"]),
    ("storage", "storage.html", ["@data", "tiles", "src", "proj", "age", "growth", "tools"]),
    ("static", "dashboard.html", ["static"]),
    ("flow", "flow.html", ["@auto", "flow", "stages", "source"]),
    ("runner", "runner.html", ["runner"]),
    ("request", "request.html", ["request"]),
    ("automation", "automation.html", ["automation"]),
]
SCRIPTLESS = {"static"}  # أجزاء تؤخذ منها الأقسام فقط (نصّها البرمجي نسخة مكرّرة من جزء آخر)

PAGES = [dict(file=f, template=t, sections=s) for f, t, s in _ROWS]
BY_FILE = {p["file"]: p for p in PAGES}
LIVE_TEMPLATES = {"dashboard.html", "sessions.html", "hourly.html", "storage.html"}  # قوالب فيها زرّ التحديث الفوري وعمر البيانات


def for_template(template):
    return [p for p in PAGES if p["template"] == template]


# مفاتيح الحمولة التي يقرؤها JS كل قسم من قوالب اللوحة؛ ما لا يطلبه أيّ قسم في الصفحة يُستبدل بفارغ من النوع نفسه فتخفّ الصفحة.
# القوالب غير المذكورة هنا (sessions وhourly وskills) تبقى حمولتها كاملة لأن كل أقسامها تقرأ المصفوفة الكبيرة نفسها.
DATA_NEEDS = {
    "dashboard.html": {
        "limits": {"plan", "plan_label", "plan_renew_day", "quota", "product"}, "tiles": {"a"}, "month": {"a"}, "h1": {"a"}, "h2": {"a"}, "h3": {"plan"},

    },
}
DATA_ALWAYS = {"models", "threshold", "min_turns", "first_day", "last_day"}  # صغيرة ويقرؤها الغلاف والمرشِّحات في كل صفحة


def prune_data(data, template, sections):
    """يُبقي من حمولة القالب ما تطلبه أقسام الصفحة، ويُفرغ الباقي (قائمة ← [] وقاموس ← {}) كي لا يتعطّل JS يقرأه."""
    needs = DATA_NEEDS.get(template)
    if needs is None:
        return data
    keep = set(DATA_ALWAYS)
    for sec in sections:
        keep |= needs.get(sec, set())
    return {k: (v if k in keep or not isinstance(v, (list, dict)) else type(v)()) for k, v in data.items()}


# قوائم الكائنات الكبيرة المنتظمة التي تُضمَّن بصيغة أعمدة (المفاتيح مرة واحدة)؛ `unpack` في ui_common.js تعيدها.
PACK_KEYS = {"dashboard.html": ("a", "plan")}


def pack_data(data, template):
    out = dict(data)
    for k in PACK_KEYS.get(template, ()):
        rows = out.get(k)
        if isinstance(rows, list) and len(rows) >= 20 and all(isinstance(r, dict) for r in rows):
            cols = list(rows[0])
            if all(list(r) == cols for r in rows):
                out[k] = {"$cols": cols, "rows": [[r[c] for c in cols] for r in rows]}
    return out
