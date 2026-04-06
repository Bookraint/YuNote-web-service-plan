-- YuNote Web — Supabase 表结构（无用户账号版）
-- 在 Supabase 控制台 SQL Editor 中执行此文件
-- 建议开发环境和生产环境使用不同的 Supabase 项目

-- ── 任务表 ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    job_id           TEXT PRIMARY KEY,
    note_id          TEXT NOT NULL,
    filename         TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'awaiting_payment',
    progress         INTEGER NOT NULL DEFAULT 0,
    stage            TEXT NOT NULL DEFAULT '等待支付',
    error            TEXT,
    scene            TEXT NOT NULL DEFAULT '通用',
    language         TEXT NOT NULL DEFAULT '',
    tier             TEXT NOT NULL DEFAULT 'standard',
    order_id         TEXT,
    upload_file_path TEXT,
    duration_sec     REAL,
    -- 支付成功后颁发；持有者凭此访问转录/总结结果
    access_token     TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 支付订单表 ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    order_id         TEXT PRIMARY KEY,
    job_id           TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    tier             TEXT NOT NULL,
    duration_sec     REAL NOT NULL,
    billed_minutes   INTEGER NOT NULL,
    amount_cents     INTEGER NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending', -- pending / paid / failed
    payment_provider TEXT,
    payment_id       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at          TIMESTAMPTZ
);

-- ── 常用索引 ────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_jobs_access_token ON jobs(access_token);
CREATE INDEX IF NOT EXISTS idx_orders_job_id     ON orders(job_id);

-- ── RLS（Row Level Security）──────────────────────────────────
-- 服务端使用 service_role key，自动绕过 RLS；无需启用。
-- ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
