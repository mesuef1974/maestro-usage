# maestro_usage (جلسة 0440 «التحوّل»)

قياس استهلاك Claude Code بالتوكن (اشتراك Max 20x: المقياس نسبة الحصة لا الدولار) في SQLite وتقارير HTML/CSV. مستقل عن الفلو: لا بطاقات ولا مضخّة ولا دفع ولا نشر. المراجع عند الحاجة (بلا استيراد @): `CHARTER.md` ثم `SPEC.md` ثم `TASKS.md`. كل عمل يُدوَّن في `LOG.md` (ماذا، لماذا، ما تحقّقتُ وما لم أتحقّق).

## الأوامر
```bash
python src/run_cycle.py --force   # تحميل ثم إعادة بناء كل التقارير (المهمة المجدولة كل دقيقة)
python src/serve.py               # 127.0.0.1:8790، عملية منفصلة تُعاد بعد إضافة مسار
python src/usage_cli.py --health  # وكذلك src/agents_cli.py --health
python src/skill_usage.py         # مسح استعمال المهارات (دقائق، يدوي ← data/skill_usage.json)
python -m pytest tests -q && ruff check src tests
```

## البنية
- `usage_ingest.py` يقرأ `~/.claude/projects/**/*.jsonl` سطرًا سطرًا إلى `usage_turns`؛ `statusline_collector.py` الحصة؛ `usage_db.py` والمخطط `schema/schema.sql`. القاعدة خارج المستودع: `C:\Users\mesue\.maestro\flow_usage.sqlite3` (نسخها في `backups\`).
- التحليل: `regime.py` و`study.py` و`startup_cost.py` و`role_groups.py`.
- `reports.build(con)` تكتب CSV وأربع صفحات (dashboard وsessions_page وhourly_page وskills_page)، كل منها وحدة `payload` + قالب `.html` يُملأ بـ`ui.render` (علامات `__SHELL_OPEN__` و`__SHELL_CLOSE__` و`__CSS__` و`__LIB__` و`__DATA__` و`__STAMP__`) ويُكتب بـ`ui.write`. صفحة جديدة: وحدة وقالب وسطر في `reports.build` ومسار في `serve.PAGES` وإدخال في `ui.NAV` و`ui.ACTIVE` (الغلاف والتنقّل الموحّد يأتيان من `ui.shell`، لا تكتب `<nav>` يدويًّا) ووسم `data-group` على الأقسام لفهرس «في هذه الصفحة» واختبار. تدقيق الواجهات: `python scripts/ux_audit.py --label <اسم>` ثم `--compare before after` (التقرير `docs/ux_audit.md`).
- `data/` و`reports/` خارج git عمدًا.

## القواعد الصلبة
- لا نصوص محادثات ولا مخرجات أدوات ولا محتوى ملفات أو أسماءها في القاعدة أو التقارير أو الشاشة (PDPPL): أرقام ومعرّفات وأوقات وأسماء نماذج وفروع ومجلدات فقط. `tests/test_whitelist.py` يفرض قائمة بيضاء؛ أضف إليها كل عمود نصّي جديد عن قصد.
- لا تطبع سطر jsonl ولا تفتحه بـRead؛ اقرأ بسكربت يخرج ملخّصًا رقميًّا.
- لا كتابة في `~/.claude` ولا `settings.json` ولا مستودعَي الحوكمة (`delivery_manager_work`) والمنصّة (`D:\shschool_mvp`) إلا بأمر صريح من المالك؛ الإعدادات عبر 0101. كل تعديل مأمور به يُسجَّل في `config_changes` بمفتاح `startup_…` وفي `LOG.md` مع نسخة احتياطية.
- لا مهمة مجدولة ولا إعداد دائم دون إذن المالك؛ أسئلته بـ`AskUserQuestion` والتوصية أولًا.
- لا أرقام مخترعة: كل رقم من القاعدة. التحميل متكرّر الأمان (إعادته لا تغيّر الأرقام ولا تضاعف الصفوف).
- git محلي فقط (بلا push ولا remote)، ورسالة عربية تنتهي بـ`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## الاتفاقات
- توقيت عالمي، أرقام لاتينية في الرسوم، RTL بخصائص منطقية، بلا مكتبات خارجية في الصفحات. تعليقات عربية فصحى بكثافة الشيفرة المحيطة، وSQL بمعاملات.
- اختبارات على بيانات صناعية صغيرة. بعد تعديل واجهة: أعد البناء وافتحها في المتصفح المدمج وافحص الكونسول قبل القول إنها تعمل.

## مزالق
- الحارس يرفض الإنجليزية في أوصاف Bash ونص الأدوات: اكتبها بالعربية.
- طباعة العربية في كونسول ويندوز تتشوّه (cp1256): `sys.stdout.reconfigure(encoding="utf-8")` أو ملف؛ لا تعتمد على `python -I` للطباعة.
- المراسلة بالصندوق لا برسائل التطبيق (حدّ عشر رسائل): `python C:/Users/mesue/delivery_manager_work/tools/inbox.py send --to 0101 --from 0440 --text "..."`؛ قصيرة والحكم أولًا، والطويلة في ملف `handover_notes` مع ملخّص خمسة أسطر.
- تحذيرات ruff المؤقتة (F401/F821) بين تعديلين تزول بوصول الثاني؛ أعد الفحص.
- مسح `skill_usage.py` يفلتر على JSON المضغوط كما في السجلات؛ اختباراته تستعمل `separators=(",", ":")`.
- جلستك تستهلك من الحصة: سياق صغير وسكربتات بملخّصات.
