"""订单创建：兑换码验证 + 积分扣除（无 Stripe，无用户账号）"""
from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import settings as cfg
from .db import get_db
from .job_store import JobStore
from .runner import start_job

logger = logging.getLogger(__name__)
router = APIRouter()


def _load_file_prompts() -> dict:
    """从文件系统读取全局 Prompt 模板。"""
    keys = ["general", "meeting", "lecture", "interview"]
    fnames = {
        "general":   "summary_general.md",
        "meeting":   "summary_meeting.md",
        "lecture":   "summary_lecture.md",
        "interview": "summary_interview.md",
    }
    out: dict[str, str] = {}
    for key in keys:
        p = cfg.PROMPTS_DIR / fnames[key]
        out[key] = p.read_text(encoding="utf-8") if p.exists() else ""
    return out


class OrderBody(BaseModel):
    job_id:         str
    tier:           str  = "standard"
    redeem_code:    str  = ""           # 用户输入的兑换码
    custom_prompts: dict = {}           # 本次提示词覆盖（不持久化）


@router.post("/api/orders")
def create_order(body: OrderBody, request: Request):
    if body.tier not in ("standard", "premium"):
        raise HTTPException(400, detail="tier 只能是 standard 或 premium")

    code_raw = body.redeem_code.strip()
    if not code_raw:
        raise HTTPException(400, detail="请输入兑换码")

    store: JobStore = request.app.state.store
    job = store.get(body.job_id)
    if not job:
        raise HTTPException(404, detail="任务不存在")
    if job["status"] != "awaiting_payment":
        raise HTTPException(400, detail="该任务已处理或已有订单，请重新上传文件")

    duration_sec: float = job.get("duration_sec") or 0.0
    billed_minutes = max(1, math.ceil(duration_sec / 60))
    price_per_min = (
        cfg.PRICE_PER_MIN_STANDARD_CREDITS
        if body.tier == "standard"
        else cfg.PRICE_PER_MIN_PREMIUM_CREDITS
    )
    credits_needed = billed_minutes * price_per_min

    db = get_db()

    # ── 开发模式：跳过验证直接激活 ──────────────────────────────────
    if cfg.DEV_SKIP_REDEEM:
        logger.info("DEV_SKIP_REDEEM=true，跳过兑换码验证 code=%s job=%s", code_raw, body.job_id)
        return _activate_job(body, store, db, job, billed_minutes, credits_needed, duration_sec, code_raw)

    # ── 查询兑换码（只读，快速校验面值）────────────────────────────
    res = db.table("redeem_codes").select("credits,status").eq("code", code_raw).execute()
    if not res.data:
        raise HTTPException(400, detail="兑换码无效，请检查后重试")

    row = res.data[0]
    if row["status"] != "unused":
        raise HTTPException(400, detail="该兑换码已被使用")
    if row["credits"] < credits_needed:
        raise HTTPException(400, detail=(
            f"兑换码积分不足：该码面值 {row['credits']} 积分，"
            f"本次需要 {credits_needed} 积分，请购买更多积分码"
        ))

    # ── 原子占用：仅当 status=unused 时才更新，防止并发重复消耗 ──
    now = datetime.utcnow().isoformat()
    claimed = db.table("redeem_codes").update({
        "status":         "used",
        "used_by_job_id": body.job_id,
        "used_at":        now,
    }).eq("code", code_raw).eq("status", "unused").execute()

    if not claimed.data:
        # 另一个并发请求抢先一步消耗了该码
        raise HTTPException(400, detail="该兑换码已被使用")

    return _activate_job(body, store, db, job, billed_minutes, credits_needed, duration_sec, code_raw, now=now)


def _activate_job(
    body: OrderBody,
    store: JobStore,
    db,
    job: dict,
    billed_minutes: int,
    credits_needed: int,
    duration_sec: float,
    code_raw: str,
    now: Optional[str] = None,      # 传入已有时间戳，避免重复生成
):
    """兑换码已原子占用后：写订单、颁发 access_token、启动任务。"""
    if now is None:
        now = datetime.utcnow().isoformat()
    order_id = uuid.uuid4().hex

    # 写订单记录
    db.table("orders").insert({
        "order_id":       order_id,
        "job_id":         body.job_id,
        "tier":           body.tier,
        "duration_sec":   duration_sec,
        "billed_minutes": billed_minutes,
        "credits_used":   credits_needed,
        "redeem_code":    code_raw,
        "status":         "paid",
        "created_at":     now,
    }).execute()

    store.update(body.job_id, tier=body.tier, order_id=order_id)

    # 颁发 access_token
    access_token = store.grant_access(body.job_id)

    # 合并 Prompt 并启动任务
    file_prompts   = _load_file_prompts()
    merged_prompts = {**file_prompts, **{k: v for k, v in body.custom_prompts.items() if v.strip()}}
    start_job(body.job_id, job["upload_file_path"], store, merged_prompts)

    logger.info("兑换码激活成功 code=%s job=%s credits=%d", code_raw, body.job_id, credits_needed)

    return {
        "order_id":     order_id,
        "access_token": access_token,
        "credits_used": credits_needed,
    }
