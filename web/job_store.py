"""Supabase-backed 任务状态存储（无用户账号版）"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Optional

from .db import get_db, reset_db

logger = logging.getLogger(__name__)


def _new_access_token() -> str:
    return secrets.token_urlsafe(24)


class JobStore:
    def create(
        self,
        job_id: str,
        note_id: str,
        filename: str,
        tier: str = "standard",
        scene: str = "通用",
        language: str = "",
        upload_file_path: str = "",
        duration_sec: Optional[float] = None,
    ) -> dict:
        now = datetime.utcnow().isoformat()
        row: dict = {
            "job_id":           job_id,
            "note_id":          note_id,
            "filename":         filename,
            "status":           "awaiting_payment",
            "progress":         0,
            "stage":            "等待支付",
            "scene":            scene,
            "language":         language,
            "tier":             tier,
            "upload_file_path": upload_file_path,
            "duration_sec":     duration_sec,
            "access_token":     None,   # 支付成功后由 order_routes 写入
            "created_at":       now,
            "updated_at":       now,
        }
        get_db().table("jobs").insert(row).execute()
        return row

    def update(self, job_id: str, **kwargs) -> None:
        kwargs["updated_at"] = datetime.utcnow().isoformat()
        try:
            get_db().table("jobs").update(kwargs).eq("job_id", job_id).execute()
        except Exception as e:
            # 连接断开时重置并重试一次
            if "RemoteProtocolError" in type(e).__name__ or "disconnect" in str(e).lower():
                logger.warning("Supabase 连接断开，正在重试 update job_id=%s", job_id)
                reset_db().table("jobs").update(kwargs).eq("job_id", job_id).execute()
            else:
                raise

    def grant_access(self, job_id: str) -> str:
        """颁发 access_token（仅在支付成功时调用），返回 token 字符串。"""
        token = _new_access_token()
        self.update(job_id, access_token=token)
        return token

    def get(self, job_id: str) -> Optional[dict]:
        res = get_db().table("jobs").select("*").eq("job_id", job_id).execute()
        return res.data[0] if res.data else None

    def list_all(self) -> list[dict]:
        res = (
            get_db()
            .table("jobs")
            .select("*")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        return res.data or []
