-- YuNote Web — Supabase 表结构（兑换码版，无用户账号）
-- 在 Supabase 控制台 SQL Editor 中执行此文件

-- ── 兑换码表 ─────────────────────────────────────────────────────
-- 由管理员在后台批量生成并写入；用户在第三方平台购买后填入使用
CREATE TABLE IF NOT EXISTS redeem_codes (
    code           TEXT PRIMARY KEY,
    credits        INTEGER NOT NULL,           -- 该码面值（积分）
    status         TEXT NOT NULL DEFAULT 'unused',  -- unused / used
    used_by_job_id TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    used_at        TIMESTAMPTZ
);

-- ── 任务表 ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    job_id           TEXT PRIMARY KEY,
    note_id          TEXT NOT NULL,
    filename         TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'awaiting_payment',
    progress         INTEGER NOT NULL DEFAULT 0,
    stage            TEXT NOT NULL DEFAULT '等待兑换',
    error            TEXT,
    scene            TEXT NOT NULL DEFAULT '通用',
    language         TEXT NOT NULL DEFAULT '',
    tier             TEXT NOT NULL DEFAULT 'standard',
    order_id         TEXT,
    upload_file_path TEXT,
    duration_sec     REAL,
    -- 兑换成功后颁发；持有者凭此访问转录/总结结果
    access_token     TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 订单表 ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    job_id          TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    tier            TEXT NOT NULL,
    duration_sec    REAL NOT NULL,
    billed_minutes  INTEGER NOT NULL,
    credits_used    INTEGER NOT NULL,           -- 本次消耗积分
    redeem_code     TEXT NOT NULL,              -- 使用的兑换码
    status          TEXT NOT NULL DEFAULT 'paid',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 常用索引 ────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_jobs_access_token  ON jobs(access_token);
CREATE INDEX IF NOT EXISTS idx_orders_job_id      ON orders(job_id);
CREATE INDEX IF NOT EXISTS idx_redeem_codes_status ON redeem_codes(status);

-- ── RLS 关闭（服务端用 service_role key 操作）─────────────────
-- ALTER TABLE jobs         ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE orders       ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE redeem_codes ENABLE ROW LEVEL SECURITY;
