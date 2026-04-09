"""管理后台接口：兑换码生成与库存查询（需 X-Admin-Key 鉴权）"""
from __future__ import annotations

import secrets
import string
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import settings as cfg
from .db import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])

# 码字符表：去掉易混淆字符 O/0/I/1/L
_CHARS = string.ascii_uppercase.replace("O", "").replace("I", "").replace("L", "") + string.digits.replace("0", "").replace("1", "")


def _require_admin(request: Request) -> None:
    key = request.headers.get("X-Admin-Key", "")
    if not cfg.ADMIN_KEY:
        raise HTTPException(503, detail="ADMIN_KEY 未配置，管理接口已禁用")
    if not secrets.compare_digest(key.encode(), cfg.ADMIN_KEY.encode()):
        raise HTTPException(401, detail="无效的管理员密钥")


def _gen_code(prefix: str = "YU") -> str:
    """生成格式为 YU-XXXX-XXXX-XXXX 的兑换码。"""
    def seg() -> str:
        return "".join(secrets.choice(_CHARS) for _ in range(4))
    return f"{prefix}-{seg()}-{seg()}-{seg()}"


# ── 生成兑换码 ────────────────────────────────────────────────────

class GenCodesBody(BaseModel):
    count:   int = Field(default=10, ge=1, le=500, description="生成数量（1-500）")
    credits: int = Field(...,         ge=1,         description="每码面值（积分）")
    prefix:  str = Field(default="YU",              description="码前缀，如 YU / VIP")


@router.post("/codes")
def gen_codes(body: GenCodesBody, request: Request):
    """
    批量生成兑换码并写入数据库。

    请求示例：
        curl -X POST http://localhost:7860/api/admin/codes \\
             -H 'X-Admin-Key: your-secret' \\
             -H 'Content-Type: application/json' \\
             -d '{"count": 50, "credits": 100}'
    """
    _require_admin(request)

    prefix = body.prefix.upper().strip("-") or "YU"
    now = datetime.utcnow().isoformat()
    db = get_db()

    # 生成并去重（极低概率碰撞，循环最多尝试 count*3 次）
    codes: list[str] = []
    attempts = 0
    max_attempts = body.count * 3
    while len(codes) < body.count and attempts < max_attempts:
        attempts += 1
        c = _gen_code(prefix)
        if c not in codes:
            codes.append(c)

    rows = [
        {"code": c, "credits": body.credits, "status": "unused", "created_at": now}
        for c in codes
    ]
    db.table("redeem_codes").insert(rows).execute()

    return {
        "generated": len(codes),
        "credits":   body.credits,
        "prefix":    prefix,
        "codes":     codes,
    }


# ── 查询库存 ──────────────────────────────────────────────────────

@router.get("/codes/stock")
def get_stock(request: Request):
    """
    查看各面值兑换码的剩余/已用数量。

    请求示例：
        curl http://localhost:7860/api/admin/codes/stock \\
             -H 'X-Admin-Key: your-secret'
    """
    _require_admin(request)

    db = get_db()
    res = db.table("redeem_codes").select("credits,status").execute()
    rows = res.data or []

    # 按面值分组统计
    summary: dict[int, dict] = {}
    for r in rows:
        c = r["credits"]
        if c not in summary:
            summary[c] = {"credits": c, "available": 0, "consumed": 0}
        if r["status"] == "unused":
            summary[c]["available"] += 1
        else:
            summary[c]["consumed"] += 1

    return {
        "total_available": sum(v["available"] for v in summary.values()),
        "by_credits": sorted(summary.values(), key=lambda x: x["credits"]),
    }


# ── 作废单张码（退款场景）────────────────────────────────────────

class VoidCodeBody(BaseModel):
    code:   str
    reason: Optional[str] = None


@router.post("/codes/void")
def void_code(body: VoidCodeBody, request: Request):
    """将一张已使用的码改回 unused（用于退款、误用等场景）。"""
    _require_admin(request)

    db = get_db()
    res = db.table("redeem_codes").select("code,status").eq("code", body.code).execute()
    if not res.data:
        raise HTTPException(404, detail="兑换码不存在")

    update_data: dict = {"status": "unused", "used_by_job_id": None, "used_at": None}
    db.table("redeem_codes").update(update_data).eq("code", body.code).execute()
    return {"ok": True, "code": body.code, "restored_to": "unused"}
