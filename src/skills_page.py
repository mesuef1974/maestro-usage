"""صفحة حصر المهارات: كل مهارة وأمر محلي أو مزامَن أو مضمَّن، مع الفائدة والاستعمال الفعلي والتكرار وتوصية الإبقاء.

الحصر من الملفات (قراءة فقط)، والاستعمال من data/skill_usage.json (skill_usage.py)، والتوصيات من CURATION أدناه (حكم بشري مبني على الأرقام).
لا يُخزَّن نصّ أي مهارة: الاسم والوصف القصير من ترويسة SKILL.md وعدد أحرف ملفها فقط.
التكلفة: مفعّلة = الاسم + الوصف في قائمة السياق، name-only = الاسم، off = صفر؛ الأحرف ÷ 3.5 تقدير للتوكن.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skill_usage  # noqa: E402
import ui  # noqa: E402

HOME = os.path.expanduser("~")
CLAUDE = os.path.join(HOME, ".claude")
PROJECT_SKILLS = "D:/shschool_mvp/.claude/skills"
FRONT = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.S)
CHARS_PER_TOKEN = 3.5
RECS = ("keep", "nameonly", "off", "archive", "clean")
NOISE = {"model", "compact", "usage", "clear", "context", "exit"}  # أوامر التطبيق المدمجة لا مهارات
ALIAS = {"anthropic-skills:docx": ("docx",), "anthropic-skills:xlsx": ("xlsx",), "anthropic-skills:consolidate-memory": ("consolidate-memory",)}

# مفتاح ← (الفائدة، التوصية، المكرَّر معها، الأفضل بينها/ملاحظة). 0 استدعاء عبر أداة Skill لا يعني بالضرورة عدم النفع:
# قد تُقرأ الملفات مباشرة أو تُستدعى بأمر مائل، لذا يُقدَّم الاستعمال دليلًا لا حكمًا.
# الملاحظات حكم بلا أعداد: عمود «استدعاءات» (من المسح) هو المصدر الوحيد للعدّ، فلا يُكتب عدد يدوي هنا كي لا ينحرف عنه.
CURATION = {
    "accessibility": ("تدقيق وتحسين وصول الويب وفق WCAG 2.2 (14 كيلوبايت).", "nameonly", ["fixing-accessibility", "web-design-mastery"],
                      "الأفضل: accessibility (الأشمل)؛ وفي واجهات SchoolOS web-design-mastery. يكفي الاسم."),
    "fixing-accessibility": ("إصلاح مشكلات ARIA والتركيز والتباين والنماذج.", "archive", ["accessibility"],
                             "أُرشفت بأمر المالك 2026-10-30. تتداخل مع accessibility كليًّا تقريبًا؛ احتفظ بواحدة."),
    "arabic-rtl-review": ("مراجعة النص العربي واتجاه RTL والطباعة وصيغ الأرقام والتواريخ ونبرة الفصحى/الخليجية.", "keep", ["web-design-mastery", "vue-comp"],
                          "من أكثر مهارات المستخدم استعمالًا، وتعمل name-only. تداخل جزئي في RTL مع web-design-mastery."),
    "adr": ("يكتب سجلّ قرار معماري (ADR) بقالب أزكية.", "keep", [], "قيمتها قرار هندسي مطلوب في قواعدك العامة؛ تكلفتها اسم فقط."),
    "django-app": ("يهيّئ تطبيق Django بهيكل SchoolOS (DDD/Clean).", "archive", ["drf-endpoint-scaffold", "schoolos-platform"],
                   "أُرشفت بأمر المالك 2026-10-30. تغطّيها schoolos-platform (خريطة الشيفرة) مع drf-endpoint-scaffold."),
    "explain-code": ("شرح الشيفرة بتشبيهات ومخطّطات.", "archive", [], "أُرشفت بأمر المالك 2026-10-30. عام يؤديه Claude بلا مهارة."),
    "lesson": ("درس تعليمي منظّم.", "archive", [], "أُرشفت بأمر المالك 2026-10-30. تأكّد أنها لا تخدم مجلد Teaching قبل الأرشفة."),
    "vue-comp": ("قالب مكوّن Vue 3 بـComposition API وRTL أولًا.", "nameonly", ["web-design-mastery"],
                 "يوافق قاعدتك العامة (Vue 3 + RTL)؛ اجعلها name-only."),
    "anthropic-skills:built-in-browser": ("دليل تشغيل متصفح التطبيق المدمج.", "nameonly", ["anthropic-skills:chrome-browser", "anthropic-skills:computer-use"],
                                          "الأفضل للمهام داخل التطبيق. مطفأة لكنها تُستدعى؛ name-only أسلم لأن تعليمات النظام تحيل إليها."),
    "anthropic-skills:chrome-browser": ("دليل Claude in Chrome (متصفحك الحقيقي).", "nameonly", ["anthropic-skills:built-in-browser"],
                                        "تُستدعى رغم off؛ name-only أسلم."),
    "anthropic-skills:computer-use": ("التحكّم بسطح المكتب بلقطات ونقرات.", "off", ["anthropic-skills:built-in-browser"], "أبقِها مطفأة."),
    "anthropic-skills:docs": ("مستندات Claude Docs القابلة للمشاركة.", "off", ["anthropic-skills:docx"],
                              "الموصل نفسه مطفأ؛ docx للملفات وdocs للمستندات المشتركة."),
    "anthropic-skills:docx": ("إنشاء وتحرير ملفات Word.", "keep", ["anthropic-skills:docs", "docx"], "name-only. الاسم القديم docx مكرَّر باسم أقدم."),
    "anthropic-skills:pdf": ("قراءة ودمج وتقسيم PDF وتعبئة نماذجه وOCR.", "keep", [], "كلفة اسم فقط؛ أبقِها."),
    "anthropic-skills:pptx": ("إنشاء وتحرير عروض PowerPoint.", "keep", [], "كلفة اسم فقط."),
    "anthropic-skills:xlsx": ("إنشاء وتحرير جداول Excel وCSV.", "keep", ["xlsx"], "تُستدعى بالاسمين والعدّ يجمعهما."),
    "cowork-plugin-management:cowork-plugin-customizer": ("تخصيص إضافة Cowork لمؤسسة.", "off", ["cowork-plugin-management:create-cowork-plugin"], "الإضافة معطّلة."),
    "cowork-plugin-management:create-cowork-plugin": ("إنشاء إضافة Cowork من الصفر.", "off", ["cowork-plugin-management:cowork-plugin-customizer"], "الإضافة معطّلة."),
    "drf-endpoint-scaffold": ("هيكل نقاط DRF: serializer وview وselector وRBAC واختبارات.", "nameonly", ["django-app", "schoolos-platform"],
                              "الأفضل لنقاط API (أحدث وأدق من django-app)."),
    "nplus1-hunter": ("اصطياد استعلامات N+1 والصفحات البطيئة.", "nameonly", [], "الاسم يكفي."),
    "owner-digest": ("مسودّة ملخّص حالة عربي للمالك أو القيادة.", "keep", ["write-spec-ar"], "name-only أصلًا؛ تختلف عن write-spec-ar (ملخّص حالة لا مواصفات)."),
    "pdppl-pii-audit": ("تدقيق البيانات الشخصية وفق قانون حماية البيانات القطري (تشفير وتسرّب وموافقة ومحو).", "nameonly", ["schoolos-source-of-truth"],
                        "الجانب التقني؛ source-of-truth للجانب القانوني."),
    "schoolos-automation": ("تحويل أي مهمة دورية إلى كود يعمل ذاتيًّا (Celery/Actions/Task Scheduler) لا مهمة Claude.", "keep", ["schoolos-watch"], "name-only أصلًا."),
    "schoolos-deploy": ("دمج PR المعتمدة والنشر خارج الدوام والتحقق والتراجع (جلسة 0601).", "keep", ["schoolos-git-safety"],
                        "name-only. تتجاور مع git-safety لكن الأولى للنشر والثانية لأوامر git."),
    "schoolos-feedback-intake": ("استقبال ملاحظات المستخدمين وفرزها (مهمة 0201).", "keep", [], "name-only أصلًا."),
    "schoolos-flow": ("مراحل سير العمل 01..08 ومن يسلّم لمن (v2.23).", "keep", ["docs/governance/flow.md (مرجع لا استيراد)"],
                      "flow.md لا يُستورد عند البدء أصلًا (W-20261026-004 في CLAUDE.md المنصّة) فالنقل منفَّذ؛ المهارة والملف مرجعان لا تكرار في السياق."),
    "schoolos-git-safety": ("أمان أوامر git في مستودع SchoolOS و‎.claude.", "nameonly", ["schoolos-deploy"], "الاسم يكفي."),
    "schoolos-load-test": ("اختبارات حمل Locust.", "nameonly", [], "الاسم يكفي."),
    "schoolos-messaging": ("قواعد الرسائل بين جلسات SchoolOS.", "nameonly", [], "الخطّافات تفرض مضمونها؛ الاسم يكفي."),
    "schoolos-migration-guard": ("أمان هجرات Django (expand/contract وNOT NULL والفهارس).", "keep", [], "مستعملة ووصفها قصير؛ أبقِها."),
    "schoolos-platform": ("خريطة شيفرة المنصّة: التطبيقات والنماذج والخدمات والأدوار.", "keep", ["django-app", "drf-endpoint-scaffold"], "الأفضل لفهم المنصّة."),
    "schoolos-preview-8500": ("معاينة المنصّة المركزية على المنفذ 8500.", "nameonly", [], "الاسم يكفي."),
    "schoolos-quality-guards": ("حرّاس الجودة وقياس ما بعد النشر.", "keep", ["schoolos-watch"], "name-only؛ تداخل جزئي مع schoolos-watch (رصد تشغيلي)."),
    "schoolos-report-ar": ("تقارير PDF وExcel عربية RTL.", "nameonly", [], "الاسم يكفي."),
    "schoolos-roadmap-sync": ("إبقاء خارطة الطريق الحيّة /roadmap/ متزامنة.", "keep", [], "name-only."),
    "schoolos-source-of-truth": ("مرجع لوائح وزارة التعليم القطرية والقرارات.", "nameonly", ["pdppl-pii-audit"], "الاسم يكفي؛ pdppl-pii-audit للجانب التقني."),
    "schoolos-watch": ("الرصد التشغيلي (جلسة 0203).", "keep", ["schoolos-quality-guards", "schoolos-automation"], "name-only؛ تداخل جزئي مع quality-guards."),
    "web-design-mastery": ("واجهات SchoolOS: طبقات CSS والرموز والوضع الداكن وRTL وHTMX.", "keep", ["artifact-design", "arabic-rtl-review", "accessibility"],
                           "الأكثر استعمالًا بين المهارات؛ الأفضل لواجهات المنصّة، وartifact-design للصفحات المستقلة."),
    "write-spec-ar": ("مواصفات ميزة (PRD) عربية من طلب المالك.", "keep", ["owner-digest"], "name-only."),
    "code-review": ("(مؤرشف) مراجعة قبل الدمج.", "archive", ["code-review (مضمَّنة)"], "مؤرشفة منذ 2026-10-25 لوجود المضمَّنة؛ تبقى مؤرشفة."),
    "morning": ("(مؤرشف) ملخّص صباحي.", "archive", [], "مؤرشفة منذ 2026-10-25."),
    "save-memory": ("(مؤرشف) حفظ معلومة في الذاكرة.", "archive", ["anthropic-skills:consolidate-memory"], "مؤرشفة منذ 2026-10-25."),
    "conventions": ("(مؤرشف) أعراف.", "archive", [], "مؤرشف."),
    "review-weekly": ("(مؤرشف) مراجعة أسبوعية.", "archive", [], "مؤرشف."),
}

# مهارات بلا ملف محلي (مضمَّنة أو مفاتيح في skillOverrides فقط): (مفتاح، مصدر، أحرف الوصف، فائدة، توصية، مكرَّر، ملاحظة).
# أحرف الوصف هنا تخمين ثابت لا قياس (لا ملف يُقاس)، فتُعرض كلفتها في الصفحة بعلامة «≈ تقدير» (حقل est في الحمولة).
VIRTUAL = [
    ("artifact-design", "مضمَّنة", 120, "تصميم صفحات HTML (الهوية والخطوط والسمات).", "keep", ["web-design-mastery", "dataviz"], "الأفضل للصفحات المستقلة."),
    ("artifact-diagramming", "مضمَّنة", 120, "مخطّطات داخل الصفحات.", "keep", ["dataviz"], "name-only."),
    ("artifact-capabilities", "مضمَّنة", 120, "قدرات تشغيلية للصفحات (بيانات حيّة وتخزين).", "keep", [], "name-only."),
    ("dataviz", "مضمَّنة", 120, "تصوير البيانات بإجراء مُتحقَّق منه.", "keep", ["artifact-design", "artifact-diagramming"], "يكمّل artifact-design."),
    ("update-config", "مضمَّنة", 120, "تعديل إعدادات Claude Code (settings.json).", "keep", ["anthropic-skills:setup-claude"], "الأفضل بين مهارات الإعداد."),
    ("simplify", "مضمَّنة", 120, "تبسيط الشيفرة المعدَّلة.", "keep", ["code-review"], "name-only."),
    ("loop", "مضمَّنة", 120, "تشغيل أمر بفاصل متكرر.", "keep", ["schedule"], "name-only."),
    ("schedule", "مضمَّنة", 120, "مهام مجدولة.", "keep", ["loop"], "name-only."),
    ("claude-api", "مضمَّنة", 120, "بناء تطبيقات على واجهة Claude البرمجية.", "keep", [], "name-only."),
    ("run", "مضمَّنة", 120, "تشغيل المشروع.", "keep", [], "name-only."),
    ("code-review (مضمَّنة)", "مضمَّنة", 700, "مراجعة التغييرات أو PR بمستويات جهد.", "nameonly", ["security-review", "code-review"],
     "مفعّلة بوصف طويل في كل جلسة؛ يكفي name-only لأنها تُستدعى بـ/code-review."),
    ("security-review", "مضمَّنة", 100, "مراجعة أمنية للتغييرات المعلّقة.", "nameonly", ["code-review (مضمَّنة)", "pdppl-pii-audit"], "name-only."),
    ("init", "مضمَّنة", 80, "إنشاء CLAUDE.md لمشروع.", "nameonly", [], "تُستدعى بـ/init عند الحاجة."),
    ("anthropic-skills:consolidate-memory", "حساب (مضمَّنة)", 0, "دمج ملفات الذاكرة وتنظيفها.", "keep", ["save-memory"], "name-only."),
    ("anthropic-skills:explain-usage", "حساب (مضمَّنة)", 0, "شرح أين ذهبت توكنات الجلسة.", "off", ["token-shield:*", "صفحات maestro_usage"],
     "الأفضل صفحات maestro_usage (قياس فعلي محلي)."),
    ("anthropic-skills:setup-claude", "حساب (مضمَّنة)", 0, "إعداد موجَّه للإضافات والأدوات.", "off", ["update-config"], "مطفأة؛ update-config تكفي."),
    ("anthropic-skills:exact-count-and-zero-tables", "مفتاح override فقط", 0, "عدّ دقيق وجداول أصفار.", "off", [], "لا ملف محلي؛ مطفأة."),
    ("anthropic-skills:lean-formal-bridge", "مفتاح override فقط", 0, "جسر بين Lean والبراهين.", "off", [], "لا ملف محلي؛ مطفأة."),
    ("anthropic-skills:lmfdb-oeis-lookup", "مفتاح override فقط", 0, "بحث LMFDB/OEIS.", "off", [], "لا ملف محلي؛ مطفأة (للرياضيات يوجد وكيل math-prof)."),
    ("claude-code-setup:claude-automation-recommender", "مفتاح override فقط", 0, "توصيات أتمتة Claude Code.", "off", ["update-config"], "مطفأة."),
    ("workflow-authoring", "مفتاح override فقط", 0, "كتابة سير عمل.", "off", [], "استُعملت في سبتمبر ثم أُطفئت؛ أعد تفعيلها عند الحاجة فقط."),
    ("plugin-authoring", "مفتاح override فقط", 0, "كتابة إضافات.", "off", [], "مطفأة."),
    ("keybindings-help", "مفتاح override فقط", 0, "اختصارات لوحة المفاتيح.", "off", [], "مطفأة."),
    ("fewer-permission-prompts", "مفتاح override فقط", 0, "تقليل مطالبات الأذونات.", "off", ["update-config"], "مطفأة."),
    ("Azkia-ux", "مفتاح override فقط", 0, "تجربة مستخدم أزكية.", "keep", [], "name-only."),
    ("token-shield:* (7 مهارات)", "إضافة معطّلة", 0, "حماية التوكنز: advisor وmonthly وoptimize وstart وstats وtoken-audit وtoken-shield.", "clean",
     ["anthropic-skills:explain-usage", "صفحات maestro_usage"],
     "الإضافة معطّلة؛ حُذفت مفاتيحها السبعة من skillOverrides بأمر المالك 2026-10-30. استُعملت token-audit في أكتوبر. maestro_usage أدقّ منها."),
]


def front(text):
    m = FRONT.match(text or "")
    out = {}
    if m:
        for key in ("description",):
            k = re.search(r"^%s:\s*(.*?)(?=^[A-Za-z][\w-]*:|\Z)" % key, m.group(1), re.S | re.M)
            if k:
                out[key] = " ".join(k.group(1).split()).strip("\"'>|- ")
    return out


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _overrides():
    try:
        return json.loads(_read(os.path.join(CLAUDE, "settings.json")) or "{}").get("skillOverrides", {})
    except ValueError:
        return {}


def disk_rows():
    """[(مفتاح، مصدر، أحرف الاسم+الوصف، أحرف الملف، الحالة)] من الملفات المحلية. الأحرف من len(text) لا بايتات القرص."""
    ov = _overrides()
    out = []

    def add(key, source, text, state=None):
        d = front(text).get("description", "")
        out.append((key, source, len(key) + len(d), len(text), state or ov.get(key, "on")))

    for p in sorted(glob.glob(os.path.join(CLAUDE, "skills", "*", "SKILL.md"))):
        add(os.path.basename(os.path.dirname(p)), "مستخدم", _read(p))
    for p in sorted(glob.glob(os.path.join(CLAUDE, "commands", "*.md"))):
        add(os.path.basename(p)[:-3], "أمر مستخدم", _read(p))
    for p in sorted(glob.glob(os.path.join(CLAUDE, "skills", "synced", "*", "*", "SKILL.md"))):
        add("anthropic-skills:" + os.path.basename(os.path.dirname(p)), "حساب (مزامَن)", _read(p))
    for p in sorted(glob.glob(os.path.join(CLAUDE, "plugins", "synced", "*", "*", "skills", "*", "SKILL.md"))):
        add(p.replace("\\", "/").split("/")[-4] + ":" + os.path.basename(os.path.dirname(p)), "إضافة حساب (مزامَنة)", _read(p))
    for p in sorted(glob.glob(PROJECT_SKILLS + "/*/SKILL.md")):
        add(os.path.basename(os.path.dirname(p)), "مشروع shschool_mvp", _read(p))
    for p in sorted(glob.glob(os.path.join(CLAUDE, "skills_archive", "**", "*.md"), recursive=True)):
        base = os.path.basename(p)
        if base != "README.md":
            name = os.path.basename(os.path.dirname(p)) if base == "SKILL.md" else base[:-3]
            add(name, "مؤرشف", _read(p), "archived")
    return out


def _tokens(chars, state):
    if state in ("off", "archived"):
        return 0
    return round(chars / CHARS_PER_TOKEN)


def _usage(usage, key):
    names = (key,) + ALIAS.get(key, ())
    n = sum(usage.get(k, {}).get("n", 0) for k in names)
    s = sum(usage.get(k, {}).get("sessions", 0) for k in names)
    last = max([usage[k]["last"] for k in names if k in usage and usage[k].get("last")] or [None], key=lambda x: x or "")
    return n, s, last


def _name_chars(key):
    return len(key)


def _after(chars, key, rec, state):
    if rec in ("archive", "off", "clean"):
        return 0
    if rec == "nameonly":
        return round(_name_chars(key) / CHARS_PER_TOKEN)
    return _tokens(chars, state) if state == "on" else round(_name_chars(key) / CHARS_PER_TOKEN) if state == "name-only" else 0


def payload(usage_data=None):
    ud = usage_data if usage_data is not None else skill_usage.load()
    usage = ud.get("usage", {})
    rows, seen = [], set()
    for key, source, chars, file_chars, state in disk_rows():
        cur = CURATION.get(key)
        benefit, rec, dups, note = cur if cur else ("غير مصنّفة بعد.", "keep", [], "لم تُصنَّف يدويًّا بعد.")
        n, s, last = _usage(usage, key)
        rows.append(dict(k=key, src=source, st=state, b=benefit, r=rec, d=dups, nt=note, n=n, s=s, last=last, file_chars=file_chars, est=False,
                         t0=_tokens(chars, state), t1=_after(chars, key, rec, state) if state != "archived" else 0))
        seen.add(key)
    for key, source, chars, benefit, rec, dups, note in VIRTUAL:
        ukey = key.replace(" (مضمَّنة)", "").split(" (")[0]
        n, s, last = _usage(usage, ukey)
        state = _overrides().get(ukey, "on" if source.startswith("مضمَّنة") and chars else "name-only")
        if key.startswith("token-shield"):
            state, n, s, last = "off", sum(v["n"] for k, v in usage.items() if k.startswith("token-shield")), 0, None
        rows.append(dict(k=key, src=source, st=state, b=benefit, r=rec, d=dups, nt=note, n=n, s=s, last=last, file_chars=None, est=bool(chars),
                         t0=_tokens(chars, state) if chars else None, t1=_after(chars, ukey, rec, state) if chars else None))
        seen.add(ukey)
    known = seen | {r["k"] for r in rows}
    gone = [dict(k=k, n=v["n"], s=v["sessions"], first=v["first"], last=v["last"], via=",".join(sorted(v["via"])))
            for k, v in sorted(usage.items(), key=lambda kv: -kv[1]["n"]) if k not in known and k not in NOISE
            and not any(k in ALIAS.get(a, ()) for a in ALIAS) and not k.startswith("token-shield")]
    tot0 = sum(r["t0"] or 0 for r in rows)
    tot1 = sum(r["t1"] or 0 for r in rows)
    return dict(rows=rows, gone=gone, scanned_at=ud.get("scanned_at"), files=ud.get("files"), t0=tot0, t1=tot1, cpt=CHARS_PER_TOKEN)


if __name__ == "__main__":
    d = payload()
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "skills.html")
    write(out, d, "يدويًّا")
    print(len(d["rows"]), "rows", d["t0"], "->", d["t1"], "tokens; gone", len(d["gone"]))
