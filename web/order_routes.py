"""订单创建（报价确认 + Stripe Checkout）和 Stripe Webhook（无用户账号版）"""
from __future__ import annotations

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

router = APIRouter()

# 存储 Stripe 支付流程中「待支付」任务的自定义 Prompt（webhook 触发时读取）
_pending_custom_prompts: dict[str, dict] = {}


def _stripe_module():
    try:
        import stripe as stripe_mod  # type: ignore
        return stripe_mod
    except ImportError:
        return None


def _stripe_checkout_ready() -> bool:
    if not cfg.STRIPE_CHECKOUT_ENABLED:
        return False
    if not cfg.stripe_secret_key_valid():
        return False
    return _stripe_module() is not None


def _load_file_prompts() -> dict:
    """从文件系统读取全局 Prompt 模板。"""
    from . import settings as _cfg
    keys = ["general", "meeting", "lecture", "interview"]
    fnames = {
        "general":   "summary_general.md",
        "meeting":   "summary_meeting.md",
        "lecture":   "summary_lecture.md",
        "interview": "summary_interview.md",
    }
    out: dict[str, str] = {}
    for key in keys:
        p = _cfg.PROMPTS_DIR / fnames[key]
        out[key] = p.read_text(encoding="utf-8") if p.exists() else ""
    return out


class OrderBody(BaseModel):
    job_id: str
    tier: str = "standard"
    custom_prompts: dict = {}   # 本次覆盖用，不持久化；key: general/meeting/lecture/interview


@router.post("/api/orders")
def create_order(body: OrderBody, request: Request):
    if body.tier not in ("standard", "premium"):
        raise HTTPException(400, detail="tier 只能是 standard 或 premium")

    store: JobStore = request.app.state.store
    job = store.get(body.job_id)
    if not job:
        raise HTTPException(404, detail="任务不存在")
    if job["status"] != "awaiting_payment":
        raise HTTPException(400, detail="任务已处理或已有订单，请重新上传文件")

    duration_sec: float = job.get("duration_sec") or 0.0
    billed_minutes = max(1, math.ceil(duration_sec / 60))
    price_per_min = (
        cfg.PRICE_PER_MIN_STANDARD_CENTS
        if body.tier == "standard"
        else cfg.PRICE_PER_MIN_PREMIUM_CENTS
    )
    amount_cents = billed_minutes * price_per_min

    order_id = uuid.uuid4().hex
    now = datetime.utcnow().isoformat()
    db = get_db()
    db.table("orders").insert({
        "order_id":       order_id,
        "job_id":         body.job_id,
        "tier":           body.tier,
        "duration_sec":   duration_sec,
        "billed_minutes": billed_minutes,
        "amount_cents":   amount_cents,
        "status":         "pending",
        "created_at":     now,
    }).execute()

    store.update(body.job_id, tier=body.tier, order_id=order_id)

    # 合并 Prompt：用户本次自定义 > 文件默认
    file_prompts = _load_file_prompts()
    merged_prompts = {**file_prompts, **{k: v for k, v in body.custom_prompts.items() if v.strip()}}

    if _stripe_checkout_ready():
        stripe = _stripe_module()
        assert stripe is not None
        stripe.api_key = cfg.STRIPE_SECRET_KEY
        # 将自定义 Prompt 暂存内存，供 webhook 回调时取用
        if merged_prompts != file_prompts:
            _pending_custom_prompts[body.job_id] = merged_prompts
        tier_label = "高级档" if body.tier == "premium" else "标准档"
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "cny",
                    "unit_amount": amount_cents,
                    "product_data": {
                        "name": f"YuNote {tier_label} · {billed_minutes} 分钟",
                    },
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{cfg.BASE_URL}/?job_id={body.job_id}&paid=1",
            cancel_url=f"{cfg.BASE_URL}/?job_id={body.job_id}&cancelled=1",
            metadata={"order_id": order_id, "job_id": body.job_id},
        )
        db.table("orders").update({
            "payment_provider": "stripe",
            "payment_id": session.id,
        }).eq("order_id", order_id).execute()
        return {"order_id": order_id, "checkout_url": session.url}

    # 未配置 Stripe → 开发模式，直接颁发 access_token 并触发任务
    db.table("orders").update({"status": "paid", "paid_at": now}).eq("order_id", order_id).execute()
    access_token = store.grant_access(body.job_id)
    start_job(body.job_id, job["upload_file_path"], store, merged_prompts)
    return {
        "order_id": order_id,
        "checkout_url": None,
        "access_token": access_token,
        "dev_auto_activated": True,
    }


@router.get("/api/jobs/{job_id}/access_token")
def poll_access_token(job_id: str, request: Request):
    """
    Stripe 支付成功后前端轮询此接口，直到拿到 access_token。
    access_token 由 webhook 在支付完成后写入。
    """
    store: JobStore = request.app.state.store
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, detail="任务不存在")
    tok = job.get("access_token")
    if not tok:
        return {"ready": False}
    return {"ready": True, "access_token": tok}


@router.post("/api/orders/webhook")
async def stripe_webhook(request: Request):
    """Stripe 支付成功回调，验签后颁发 access_token 并触发任务。"""
    if not cfg.STRIPE_CHECKOUT_ENABLED:
        raise HTTPException(501, detail="Stripe Checkout 未启用")
    if not cfg.stripe_secret_key_valid():
        raise HTTPException(501, detail="STRIPE_SECRET_KEY 无效或未配置")

    stripe = _stripe_module()
    if stripe is None:
        raise HTTPException(501, detail="stripe 包未安装，请执行 pip install stripe")

    stripe.api_key = cfg.STRIPE_SECRET_KEY

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, cfg.STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, detail="Webhook 签名验证失败")
    except Exception as exc:
        raise HTTPException(400, detail=str(exc))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id: Optional[str] = session.get("metadata", {}).get("order_id")
        job_id: Optional[str]   = session.get("metadata", {}).get("job_id")
        if order_id and job_id:
            db = get_db()
            now = datetime.utcnow().isoformat()
            db.table("orders").update({
                "status":   "paid",
                "payment_id": session["id"],
                "paid_at":  now,
            }).eq("order_id", order_id).execute()

            store: JobStore = request.app.state.store
            job = store.get(job_id)
            if job and job.get("upload_file_path"):
                access_token = store.grant_access(job_id)
                prompts = _pending_custom_prompts.pop(job_id, None) or _load_file_prompts()
                start_job(job_id, job["upload_file_path"], store, prompts)

    return {"ok": True}
