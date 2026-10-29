# المواصفة: قاعدة استهلاك Claude Code المحلية

## 1. مصادر البيانات (من أين تقرئين)

### أ. سجلات الجلسات jsonl (المصدر الرئيس، تاريخي)
- المسار: `C:\Users\mesue\.claude\projects\<مجلد-المشروع>\<معرّف-الجلسة-CLI>.jsonl`، وقد توجد سجلات الوكلاء الفرعيين (subagents) تحت مجلد بجوار السجل أو داخله: اكتشفي البنية بسكربت قبل الافتراض.
- كل سطر JSON. السطر الذي يهمّك `type == "assistant"`، وفيه:
  `message.id`، `message.model`، `message.usage` = `input_tokens` و`cache_creation_input_tokens` و`cache_read_input_tokens` و`output_tokens` (وفي `output_tokens_details` قد يوجد `thinking_tokens`)، و`timestamp`، و`sessionId`، و`gitBranch`، و`cwd`، و`isSidechain`، و`requestId`.
- الردّ الواحد يظهر في أكثر من سطر (بثّ تدريجي): في سجل جلسة 0101 (99553e2f-5356-49f2-aed0-1648322c6b41، نحو 22.7 ميغابايت) 1925 سطرًا تعطي 1026 ردًّا فريدًا. القاعدة: أزيلي التكرار بـ`message.id` واحتفظي بالسطر ذي أكبر `output_tokens` (تحقّقي من ذلك على بيانات حقيقية قبل اعتماده؛ إن كان `usage` تراكميًّا في الأسطر المتتابعة فهو الأخير).
- معرّف الجلسة في اسم الملف هو معرّف CLI وليس معرّف تطبيق سطح المكتب (`local_...`). ربطه برقم الجلسة (0101 وغيرها) مهمّة استقصاء في المرحلة 0: ابحثي أولًا في بنية السجل نفسها (سطور من نوع عنوان الجلسة إن وُجدت)، ثم في `C:\Users\mesue\delivery_manager_work\tools\session_directory.py` وملفات `ledger/inbox/*.beat` (للقراءة فقط). إن تعذّر الربط الآلي فاحفظي `number` فارغًا واربطي بما تعرفين (الفرع/المجلد) ووثّقي ما لم يُربط.
- تحذير الاحتفاظ: Claude Code يحذف ملفات الجلسات الأقدم من `cleanupPeriodDays` (افتراضيًا 30 يومًا، وغير مضبوط في إعدادات المالك). فما قبل نحو 2026-09-29 قد يكون مفقودًا من السجلات بينما `/stats` يحتفظ بمجاميعه. استوردي كل ما بقي فورًا في المرحلة 1 قبل أن يُحذف، وارفعي لـ0101 اقتراح رفع `cleanupPeriodDays` (بنص التعديل وخطره).

### ب. `statusLine` (حيّ، يعطي الحصة)
Claude Code يشغّل سكربتًا تحدّده بعد كل ردّ ويمرّر له JSON على stdin، وفيه (من التوثيق https://code.claude.com/docs/en/statusline ):
- `session_id` و`transcript_path`.
- `rate_limits.five_hour.used_percentage` و`.resets_at`، و`rate_limits.seven_day.used_percentage` و`.resets_at` (لمشتركي Pro وMax فقط، بعد أول ردّ في الجلسة، وقد تغيب كل نافذة بمفردها: تعاملي مع الغياب).
- `context_window.context_window_size` و`used_percentage` و`current_usage` (التفصيل بالمكوّنات).
- `prompt_cache` (نسبة الإصابة `hit_ratio` والإخفاقات وهل الذاكرة دافئة)، وحقولها في قسم prompt cache fields من الصفحة نفسها.
- `cost.total_cost_usd` (تقدير بسعر القائمة؛ ليس فاتورة: خطّتك اشتراك ثابت).
- المطلوب: سكربت قصير جدًّا وسريع يُلحق سطرًا JSON (الحقول الرقمية والمعرّفات فقط) إلى ملف تجميع `C:\Users\mesue\maestro_usage\data\statusline_spool.jsonl`، ويطبع للشريط سطرًا قصيرًا (مثل نسبة الأسبوع) أو لا شيء. لا يكتب SQLite مباشرةً (لتفادي القفل والبطء)، ولا يفشل بصمت ولا يعطّل الجلسة أبدًا (أي خطأ يُبتلع ويُسجَّل في ملف أخطاء). ثم يحمّل المحمِّل الملف إلى القاعدة.
- التثبيت (سطر `statusLine` في settings.json) يمرّ عبر 0101 (محظور عليك تعديله).

### ج. أمر `get_usage` (احتياط للتحقق)
إن توفّرت لك أداة `mcp__ccd_session_mgmt__get_usage` فهي تعطي نسب الحصة الحالية (5 ساعات، أسبوعي عام، أسبوعي Fable). وإلا فاطلبيها من 0101 عند الحاجة. تسجَّل في `plan_snapshots` بمصدر `get_usage`.

### د. مرجع للقراءة فقط: مراقب Codex المحلي
`C:\Users\mesue\.codex\worktrees\main-unification\local-pen-studio\scripts\usage_monitor\` فيه تصميم ناجح لنفس الغرض لـCodex. خذي الأفكار ولا تنسخي الشيفرة كما هي:
- `codex_usage_logger.py`: تحميل تزايدي بجدول مواضع (`usage_sources`)؛ يتجاهل السطر الناقص في آخر الملف؛ يعيد من الصفر إن صغر الملف؛ لا يحفظ نصوصًا.
- `usage_database.py` و`migrations/`: مخطط مرقّم.
- `backup_usage_database.py`: نسخة بواجهة SQLite Backup + `integrity_check`.
- `dashboard.html` و`dashboard.js`: لوحة بلا إطار مع Canvas (للتصميم فقط؛ لوحتك أولًا صفحة HTML ساكنة).
- لا تعدّلي شيئًا هناك.

### هـ. دفاتر الفلو (قراءة فقط، لاحقًا)
`C:\Users\mesue\delivery_manager_work\ledger\events.jsonl` لربط الجلسات بالبطاقات (مرحلة متأخّرة اختيارية). لا تبدئي به قبل المرحلة 4.

## 2. المخطط (schema/schema.sql، مرقّم بإصدار)

يجب أن يعمل على SQLite الآن وأن يبقى قابلًا للنقل إلى Postgres: لا تستعملي ميزات خاصّة بـSQLite. فعّلي WAL و`foreign_keys` و`busy_timeout`.

| الجدول | المفتاح | الأعمدة |
|---|---|---|
| `sessions` | `session_key` (معرّف CLI) | `number` (0101…) NULL، `title` NULL، `cwd`، `branch`، `first_seen`، `last_seen` |
| `usage_turns` | `message_id` | `session_key` FK، `ts`، `model`، `input_tokens`، `cache_creation_tokens`، `cache_read_tokens`، `output_tokens`، `thinking_tokens`، `is_sidechain`، `request_id`، `source_path` |
| `ingest_state` | `source_path` | `offset_bytes`، `size_bytes`، `mtime`، `updated_at` |
| `plan_snapshots` | `id` | `ts`، `session_key` NULL، `five_hour_pct`، `five_hour_resets_at`، `seven_day_pct`، `seven_day_resets_at`، `source` (statusline/get_usage)، `plan` |
| `statusline_samples` | `id` | `ts`، `session_key`، `context_size`، `context_used_pct`، حقول `current_usage` الأربعة، `cache_hit_ratio`، `cache_warm`، `cost_usd` |
| `config_changes` | `id` | `ts`، `key`، `old_value`، `new_value`، `note` |

بذور `config_changes` (قرارات المالك في 2026-10-29): `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` من 9 إلى 45 ثم من 45 إلى 25 (كلاهما في اليوم نفسه، عتبة الضغط التلقائي، في `C:\Users\mesue\.claude\settings.json`). كلّ تغيير إعداد جديد يخبرك به 0101 يُضاف هنا.

مفاتيح الأمان: `INSERT OR IGNORE` على `message_id`؛ التحميل داخل معاملة؛ لا تحذفي صفوفًا خامًا قبل 90 يومًا، ثم تُجمَّع يوميًّا في جدول `usage_daily` (خطّة الاحتفاظ تُعرَض على المالك قبل تنفيذ أي حذف).

عروض (VIEW) لا جداول للاستعلامات الثقيلة: `v_session_daily` و`v_model_daily` و`v_cache_ratio` (قراءة الذاكرة ÷ المخرجات لكل جلسة).

## 3. التقارير الخمسة (معيار «انتهى» للمشروع)

1. توكنز كل جلسة موزّعة على النموذج واليوم، مرتّبة بنسبة قراءة الذاكرة إلى المخرجات.
2. أسوأ عشر جلسات سياقًا: سياق الردّ (`input + cache_creation + cache_read`) فوق 300 ألف، مع عدد الردود.
3. مقارنة سبعة أيام قبل كل تغيير في `config_changes` وسبعة بعده، بالمقاييس نفسها.
4. نسبة الحصة الأسبوعية حسب اليوم (من `plan_snapshots`).
5. كلفة الدورة الدورية في جلسة 0101 (كل 5 دقائق): بلا نصوص. تُميَّز بنمط زمني (ردود على فواصل نحو 5 دقائق) وبمخرجات صغيرة، وتُذكر في التقرير حدود هذا التمييز ودرجة الثقة فيه.

الإخراج: صفحة HTML ساكنة تُولَّد محليًّا إلى `C:\Users\mesue\maestro_usage\reports\` (RTL، عربية، بلا مكتبات خارجية، تعمل بالفتح المباشر من الملف) مع ملف CSV لكل تقرير. لا خادم ولا Django في هذه المرحلة.

## 4. التحقق (قبل أن تقولي «صحيح»)

- التكرار: على سجل حقيقي، عدد صفوف `usage_turns` لجلسة = عدد `message.id` الفريدة في سجلها (وليس عدد الأسطر).
- المقارنة مع `/stats` (كل الزمن، لقطة المالك 2026-10-29): الإجمالي 78.5 مليار؛ المدخلات 952.8 ألفًا؛ المخرجات 184.1 مليونًا؛ قراءة الذاكرة 76.9 مليارًا؛ كتابة الذاكرة 1.5 مليار؛ 1165 جلسة؛ Sonnet 5.5 نحو 37.9% وSonnet 5 نحو 37.3% وOpus 5 نحو 14.9% وOpus 5.5 نحو 6.2% وFable 5.1 نحو 1.8% وHaiku 5.5 نحو 1.3%. يُتوقع فرق لأن `/stats` يحتفظ بما حُذفت سجلّاته؛ فسّري الفرق (حدود الاحتفاظ) بالقياس لا بالتخمين، وقدّريه.
- لا نصوص: اختبار يفحص القائمة البيضاء للحقول النصية.
- التكرار الآمن: تشغيلان متتاليان على الملفات نفسها يعطيان العدّادات نفسها.
- السلامة: `PRAGMA integrity_check` بعد كل نسخة احتياطية.
