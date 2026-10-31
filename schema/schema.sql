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
