-- مخطط قاعدة استهلاك Claude Code المحلية (الإصدار 1). نصوص القاعدة معرّفات وأرقام فقط (راجع tests/test_whitelist.py).
-- محمول إلى Postgres: لا ميزات خاصة بـSQLite في الجداول.
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_key   TEXT PRIMARY KEY,          -- معرّف CLI
    number        TEXT,                      -- 0101… (NULL لغير جلسات الفلو)
    number_source TEXT,                      -- custom-title | app | agents | NULL
    title         TEXT,                      -- يبقى NULL عمدًا: العناوين قد تحمل بيانات
    cwd           TEXT,
    branch        TEXT,
    first_seen    TEXT,
    last_seen     TEXT
);

CREATE TABLE IF NOT EXISTS ingest_state (
    source_path  TEXT PRIMARY KEY,           -- نسبةً إلى ‎~/.claude/projects
    offset_bytes INTEGER NOT NULL,
    size_bytes   INTEGER NOT NULL,
    mtime        REAL NOT NULL,
    updated_at   TEXT NOT NULL,
    first_ts     TEXT,                       -- أقدم timestamp في الملف (لإسناد المكرّرات)
    session_key  TEXT,                       -- الجلسة المالكة للملف (من اسمه/مجلده)
    last_origin  TEXT                        -- آخر turnOrigin مرّ في الملف (لتحميل تزايدي)
);

CREATE TABLE IF NOT EXISTS usage_turns (
    message_id            TEXT PRIMARY KEY,
    session_key           TEXT NOT NULL REFERENCES sessions(session_key),
    ts                    TEXT NOT NULL,
    model                 TEXT NOT NULL,
    input_tokens          INTEGER NOT NULL,
    cache_creation_tokens INTEGER NOT NULL,
    cache_read_tokens     INTEGER NOT NULL,
    output_tokens         INTEGER NOT NULL,
    thinking_tokens       INTEGER NOT NULL DEFAULT 0,
    is_sidechain          INTEGER NOT NULL DEFAULT 0,
    request_id            TEXT,
    source_path           TEXT NOT NULL,
    sid_rank              INTEGER,                   -- 0 إن كان اسم ملف المالك = sessionId السطر (الأصل)، وإلا 1؛ لإسناد حتمي للمكرّرات
    turn_origin           TEXT,                      -- human|peer|sdk|scheduled|task_notification (فئة من سطر user السابق؛ NULL للوكلاء الفرعيين)
    cc_1h                 INTEGER,                   -- من cache_creation_input_tokens ما كُتب بمدة صلاحية ساعة (NULL قبل الاستيعاب أو إن غاب الحقل)
    cc_5m                 INTEGER                    -- وما كُتب بخمس دقائق (الوكلاء الفرعيون والضغط والعناوين)
);
CREATE INDEX IF NOT EXISTS ix_turns_session ON usage_turns(session_key, ts);
CREATE INDEX IF NOT EXISTS ix_turns_ts ON usage_turns(ts);

CREATE TABLE IF NOT EXISTS plan_snapshots (
    id                  INTEGER PRIMARY KEY,
    ts                  TEXT NOT NULL,
    session_key         TEXT,
    five_hour_pct       REAL,
    five_hour_resets_at TEXT,
    seven_day_pct       REAL,
    seven_day_resets_at TEXT,
    source              TEXT NOT NULL,       -- statusline | get_usage | cli_usage
    plan                TEXT,
    fable_pct           REAL,                -- نافذة Fable الأسبوعية (cli_usage فقط)
    fable_resets_at     TEXT
);

-- عدّاد الطلبات والجلسات على الجهاز كما يقرؤه claude -p "/usage" (للمطابقة مع قاعدتنا)
CREATE TABLE IF NOT EXISTS cli_usage_counts (
    id        INTEGER PRIMARY KEY,
    ts        TEXT NOT NULL,
    window    TEXT NOT NULL,             -- 24h | 7d
    requests  INTEGER NOT NULL,
    sessions  INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_cli_usage_counts ON cli_usage_counts(ts, window);

CREATE TABLE IF NOT EXISTS statusline_samples (
    id                    INTEGER PRIMARY KEY,
    ts                    TEXT NOT NULL,
    session_key           TEXT,
    context_size          INTEGER,
    context_used_pct      REAL,
    cu_input_tokens       INTEGER,
    cu_output_tokens      INTEGER,
    cu_cache_creation     INTEGER,
    cu_cache_read         INTEGER,
    cache_hit_ratio       REAL,
    cache_warm            INTEGER,
    cost_usd              REAL
);

CREATE TABLE IF NOT EXISTS config_changes (
    id        INTEGER PRIMARY KEY,
    ts        TEXT NOT NULL,
    key       TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    note      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_config_changes ON config_changes(ts, key, old_value, new_value);

CREATE VIEW IF NOT EXISTS v_session_daily AS
SELECT session_key, substr(ts, 1, 10) AS day, model, COUNT(*) AS turns,
       SUM(input_tokens) AS input_tokens, SUM(cache_creation_tokens) AS cache_creation_tokens,
       SUM(cache_read_tokens) AS cache_read_tokens, SUM(output_tokens) AS output_tokens
FROM usage_turns GROUP BY session_key, substr(ts, 1, 10), model;

CREATE VIEW IF NOT EXISTS v_model_daily AS
SELECT substr(ts, 1, 10) AS day, model, COUNT(*) AS turns,
       SUM(input_tokens) AS input_tokens, SUM(cache_creation_tokens) AS cache_creation_tokens,
       SUM(cache_read_tokens) AS cache_read_tokens, SUM(output_tokens) AS output_tokens
FROM usage_turns GROUP BY substr(ts, 1, 10), model;

CREATE VIEW IF NOT EXISTS v_cache_ratio AS
SELECT session_key, COUNT(*) AS turns, SUM(cache_read_tokens) AS cache_read_tokens,
       SUM(output_tokens) AS output_tokens,
       CASE WHEN SUM(output_tokens) > 0 THEN 1.0 * SUM(cache_read_tokens) / SUM(output_tokens) END AS read_per_output
FROM usage_turns GROUP BY session_key;

CREATE UNIQUE INDEX IF NOT EXISTS ux_statusline_samples ON statusline_samples(ts, session_key);
CREATE UNIQUE INDEX IF NOT EXISTS ux_plan_snapshots ON plan_snapshots(ts, session_key, source);

-- تشغيلات الجلسات الحيّة من `claude agents --json`: صف لكل (جلسة، وقت بدء عملية)؛ تغيّر startedAt لجلسة = إعادة تشغيل/استئناف.
-- يُحفظ رقم الجلسة (4 أرقام) لا الاسم الكامل، لأن الأسماء نصوص بشرية.
CREATE TABLE IF NOT EXISTS agent_starts (
    session_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    number     TEXT,
    kind       TEXT,
    pid        INTEGER,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    PRIMARY KEY (session_id, started_at)
);

-- كلفة بدء الجلسة: سياق أول ردّ رئيس لكل جلسة (إدخال + كتابة ذاكرة + قراءتها)؛ صف لكل جلسة، يبقى لو حُذفت السجلات.
CREATE TABLE IF NOT EXISTS startup_samples (
    session_key           TEXT PRIMARY KEY,
    ts                    TEXT NOT NULL,
    ctx                   INTEGER NOT NULL,
    input_tokens          INTEGER,
    cache_creation_tokens INTEGER,
    cache_read_tokens     INTEGER,
    model                 TEXT,
    origin                TEXT,
    folder                TEXT,                      -- آخر مكوّن من مجلد العمل (تسمية folder_label)
    proj                  TEXT,                      -- مجلد المشروع في ~/.claude/projects
    cc_version            TEXT                       -- إصدار Claude Code من أول سطر ذي إصدار في السجل
);
CREATE INDEX IF NOT EXISTS ix_startup_samples_ts ON startup_samples(ts);

-- بصمات مصادر السياق الثابت (إعدادات البدء، التعليمات، المهارات، الذاكرة). تُحفظ البصمة والحجم فقط، لا المحتوى.
-- الصف الأول لكل بند خط الأساس، وكل صف بعده تغيير مكتشف آليًّا بزمنه.
CREATE TABLE IF NOT EXISTS config_fingerprints (
    ts    TEXT NOT NULL,
    item  TEXT NOT NULL,
    sha   TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    PRIMARY KEY (item, ts)
);

-- حجم بيانات كلود المحلية (~/.claude): لقطة كل ساعة (الإجمالي) وصفوف مجمّعة بحسب المجلد الأعلى والمشروع والامتداد. لا أسماء ملفات.
CREATE TABLE IF NOT EXISTS storage_scans (
    ts          TEXT PRIMARY KEY,
    total_bytes INTEGER NOT NULL,
    files       INTEGER NOT NULL,
    seconds     REAL
);
CREATE TABLE IF NOT EXISTS storage_dirs (
    ts     TEXT NOT NULL,
    kind   TEXT NOT NULL,                      -- top | proj | ext
    name   TEXT NOT NULL,                      -- اسم مجلد أو امتداد
    bytes  INTEGER NOT NULL,
    files  INTEGER NOT NULL,
    newest TEXT,
    oldest TEXT,
    b7     INTEGER NOT NULL DEFAULT 0,         -- بايتات بحسب عمر الملف: ≤7 و≤30 و≤90 و>90 يومًا
    b30    INTEGER NOT NULL DEFAULT 0,
    b90    INTEGER NOT NULL DEFAULT 0,
    b90p   INTEGER NOT NULL DEFAULT 0,
    jsonl  INTEGER NOT NULL DEFAULT 0,         -- عدد سجلات الجلسات (للمشاريع)
    sub    INTEGER NOT NULL DEFAULT 0,         -- بايتات الوكلاء الفرعيين (للمشاريع)
    PRIMARY KEY (ts, kind, name)
);
-- عمليات تحرير المساحة: نقل إلى الحجر واسترجاع وإفراغ نهائي؛ قائمة الملفات في manifest.json داخل مجلد الحجر لا هنا.
CREATE TABLE IF NOT EXISTS storage_actions (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     TEXT NOT NULL,
    action TEXT NOT NULL,                      -- quarantine | restore | purge
    grp    TEXT NOT NULL,
    days   INTEGER NOT NULL DEFAULT 0,
    files  INTEGER NOT NULL DEFAULT 0,
    bytes  INTEGER NOT NULL DEFAULT 0,
    qdir   TEXT NOT NULL,                      -- مجلد الحجر
    status TEXT NOT NULL                       -- quarantined | restored | purged | done
);

-- الإصدار 7 (تطبيع): بُعد النماذج مرّة واحدة، والتجميعات تشير إليه بمفتاح أجنبي بدل تكرار الاسم نصًّا في كل صف.
CREATE TABLE IF NOT EXISTS models (
    model_id   INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,         -- كما يرد في usage_turns.model
    family     TEXT,                         -- sonnet | opus | haiku | fable | NULL (مشتقّ من الاسم)
    first_seen TEXT,
    last_seen  TEXT
);

-- تجميعات الاستهلاك (يوم/أسبوع/شهر × نموذج)؛ مشتقّة تُعاد كتابتها كاملةً من usage_turns في معاملة واحدة (rollups.refresh).
-- الأسبوع يبدأ الاثنين بالتوقيت العالمي؛ period_start يوم البداية (YYYY-MM-DD). جدول عادي بلا ميزات SQLite فينتقل إلى Postgres كما هو.
CREATE TABLE IF NOT EXISTS usage_rollups (
    grain                 TEXT NOT NULL CHECK (grain IN ('day', 'week', 'month')),
    period_start          TEXT NOT NULL,
    model_id              INTEGER NOT NULL REFERENCES models(model_id),
    turns                 INTEGER NOT NULL,
    sessions              INTEGER NOT NULL,
    input_tokens          INTEGER NOT NULL,
    cache_creation_tokens INTEGER NOT NULL,
    cache_read_tokens     INTEGER NOT NULL,
    output_tokens         INTEGER NOT NULL,
    thinking_tokens       INTEGER NOT NULL DEFAULT 0,
    refreshed_at          TEXT NOT NULL,
    PRIMARY KEY (grain, period_start, model_id)
);
CREATE INDEX IF NOT EXISTS ix_rollups_period ON usage_rollups(grain, period_start);
CREATE INDEX IF NOT EXISTS ix_turns_model_ts ON usage_turns(model, ts);

CREATE VIEW IF NOT EXISTS v_usage_rollups AS
SELECT r.grain, r.period_start, m.name AS model, m.family, r.turns, r.sessions, r.input_tokens, r.cache_creation_tokens,
       r.cache_read_tokens, r.output_tokens, r.thinking_tokens
FROM usage_rollups r JOIN models m ON m.model_id = r.model_id;

-- إجمالي كل جلسة: أول وآخر نشاط وعدد الأدوار والنماذج المستعملة.
CREATE VIEW IF NOT EXISTS v_session_totals AS
SELECT session_key, MIN(ts) AS first_ts, MAX(ts) AS last_ts, COUNT(*) AS turns, COUNT(DISTINCT model) AS models,
       SUM(input_tokens) AS input_tokens, SUM(cache_creation_tokens) AS cache_creation_tokens,
       SUM(cache_read_tokens) AS cache_read_tokens, SUM(output_tokens) AS output_tokens
FROM usage_turns GROUP BY session_key;

-- تاريخ الأتمتة (v8): فهرسٌ مشتقٌّ من دفتر الحوكمة يُعاد بناؤه كاملًا، فلا مصدرَ فيه غيرُ الدفتر.
-- معرّفات وتصنيفات وأوقات وأرقام فقط؛ نصوص البطاقات تبقى في الدفتر وتُقرأ عند العرض.
CREATE TABLE IF NOT EXISTS auto_cards (
    card_id TEXT PRIMARY KEY,
    era TEXT NOT NULL,           -- auto: مرّت بالمشغّل، manual: قبله
    source TEXT,
    req_type_key TEXT,
    size_key TEXT,
    priority TEXT,
    approval_key TEXT,
    state TEXT NOT NULL,
    stage_rank INTEGER NOT NULL, -- أبعد مرحلة: 0 دخلت، 1 بدأ العمل، 2 طلب دمج، 3 اندمجت، 4 نُشرت
    pr INTEGER,
    created_ts TEXT,
    first_run_ts TEXT,
    pr_ts TEXT,
    merged_ts TEXT,
    ended_ts TEXT,
    last_ts TEXT,
    duration_s INTEGER,
    cost_usd REAL NOT NULL DEFAULT 0,
    runs INTEGER NOT NULL DEFAULT 0,
    turns INTEGER NOT NULL DEFAULT 0,
    ci_fixes INTEGER NOT NULL DEFAULT 0,
    stop_key TEXT
);
CREATE INDEX IF NOT EXISTS idx_auto_cards_era ON auto_cards(era, created_ts);
CREATE TABLE IF NOT EXISTS auto_events (
    card_id TEXT NOT NULL,
    seq INTEGER NOT NULL,        -- ترتيب الحدث في بطاقته داخل الدفتر، وبه يُجلب نصّه عند العرض
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    state TEXT,
    op TEXT,
    model TEXT,
    cost_usd REAL,
    turns INTEGER,
    PRIMARY KEY (card_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_auto_events_ts ON auto_events(ts);
CREATE TABLE IF NOT EXISTS auto_sync (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    events INTEGER NOT NULL,
    cards INTEGER NOT NULL,
    synced_at TEXT NOT NULL
);
