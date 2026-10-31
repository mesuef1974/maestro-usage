"""سجلّ صفحات المنصة: مصدر وحيد للتنقّل والعناوين والأقسام التي تُبقيها كل صفحة من قالبها.
القالب الواحد يخدم عدّة صفحات: `ui.render` يحذف من القالب كل قسم لا يرد في `sections` الصفحة."""

# أيقونات الشريط الجانبي (مسارات داخل svg 24x24، خطّ لا تعبئة)
ICON = {
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
}

GROUPS = ["نظرة عامة", "الحصة والزمن", "الاستهلاك", "الأدوار والجلسات", "دراسات", "البيانات"]

# (الملف، القالب، العنوان، السطر التمهيدي، المجموعة، الأيقونة، الأقسام بالترتيب)
_ROWS = [
    ("index.html", "dashboard.html", "نظرة عامة",
     "الحصة الآن وتوكنز كل شهر، ثم دليل صفحات المنصة.", "نظرة عامة", "home", ["limits", "month", "hub"]),
    ("plan.html", "dashboard.html", "الحصة الأسبوعية",
     "نسبة الحصة المستهلكة عبر الأسبوع ومقارنتها بالتوكنات المقاسة.", "الحصة والزمن", "gauge", ["limits", "filters", "h3"]),
    ("hourly.html", "hourly.html", "الإجمالي بالساعة",
     "منحنى التوكنات التراكمي بالساعة ومؤشرات الحصة.", "الحصة والزمن", "clock", ["filters", "tiles", "hq", "hp", "ht", "defs"]),
    ("pressure.html", "hourly.html", "ضغط السياق لكل دور",
     "ضغط السياق % وبطاقة كل دور على المحور الزمني.", "الحصة والزمن", "wave", ["filters", "hp", "hpr", "hr", "defs"]),
    ("cache.html", "dashboard.html", "التخزين المؤقت",
     "حصّة القراءة من الكاش لكل نموذج وأثرها في التوكنات.", "الاستهلاك", "layers", ["filters", "tiles", "h1"]),
    ("origins.html", "dashboard.html", "مصادر الاستهلاك",
     "من أين يأتي الاستهلاك: الأصل والنموذج.", "الاستهلاك", "pie", ["filters", "h2"]),
    ("heavy.html", "dashboard.html", "أثقل الجلسات",
     "الجلسات الأعلى سياقًا وكلفة في الفترة المختارة.", "الاستهلاك", "list", ["filters", "h4"]),
    ("roles.html", "sessions.html", "ترتيب الأدوار",
     "استهلاك كل دور وضغطه ومساره اليومي.", "الأدوار والجلسات", "users", ["filters", "tiles", "rank", "roles", "defs"]),
    ("regimes.html", "sessions.html", "أنظمة التشغيل",
     "أنظمة السياق والإيقاظ التي مرّت بها الأدوار.", "الأدوار والجلسات", "split", ["filters", "tiles", "rg", "defs"]),
    ("compare.html", "sessions.html", "تفصيل ومقارنة",
     "تفصيل دور واحد ومقارنته بدور آخر.", "الأدوار والجلسات", "bars", ["filters", "detail", "cmp", "defs"]),
    ("autocompact.html", "dashboard.html", "الضغط التلقائي",
     "أثر الضغط التلقائي للسياق قبل التغيير وبعده.", "دراسات", "zap", ["filters", "h5"]),
    ("startup.html", "dashboard.html", "كلفة البدء",
     "كلفة بدء الجلسة بالتوكن عبر الأيام.", "دراسات", "power", ["h6"]),
    ("skills.html", "skills.html", "حصر المهارات",
     "كل مهارة وأمر: فائدتها واستعمالها الفعلي وتوصية الإبقاء أو الأرشفة.", "دراسات", "grid", ["tiles", "filters2", "tbl", "gone", "defs"]),
    ("data.html", "dashboard.html", "الجداول والملفات",
     "الجداول الساكنة والتحفظات وملفات CSV.", "البيانات", "db", ["static"]),
]

PAGES = [dict(file=f, template=t, title=ti, lede=le, group=g, icon=ic, sections=s) for f, t, ti, le, g, ic, s in _ROWS]
BY_FILE = {p["file"]: p for p in PAGES}
LIVE_TEMPLATES = {"dashboard.html", "sessions.html", "hourly.html"}  # قوالب فيها زرّ التحديث الفوري وعمر البيانات


def for_template(template):
    return [p for p in PAGES if p["template"] == template]


# مفاتيح الحمولة التي يقرؤها JS كل قسم من قوالب اللوحة؛ ما لا يطلبه أيّ قسم في الصفحة يُستبدل بفارغ من النوع نفسه فتخفّ الصفحة.
# القوالب غير المذكورة هنا (sessions وhourly وskills) تبقى حمولتها كاملة لأن كل أقسامها تقرأ المصفوفة الكبيرة نفسها.
DATA_NEEDS = {
    "dashboard.html": {
        "limits": {"plan", "plan_label", "plan_renew_day"}, "tiles": {"a"}, "month": {"a"}, "h1": {"a"}, "h2": {"a"}, "h3": {"plan"},
        "h4": {"b", "sessions"}, "h5": {"a", "changes"}, "h6": {"startup"},
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
PACK_KEYS = {"dashboard.html": ("a", "b", "plan"), "sessions.html": ("c",), "hourly.html": ("h", "plan")}


def pack_data(data, template):
    out = dict(data)
    for k in PACK_KEYS.get(template, ()):
        rows = out.get(k)
        if isinstance(rows, list) and len(rows) >= 20 and all(isinstance(r, dict) for r in rows):
            cols = list(rows[0])
            if all(list(r) == cols for r in rows):
                out[k] = {"$cols": cols, "rows": [[r[c] for c in cols] for r in rows]}
    return out
