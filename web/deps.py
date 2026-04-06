"""FastAPI 依赖项：凭 access_token 查找并验证任务"""
from __future__ import annotations

from fastapi import HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import get_db

_bearer = HTTPBearer(auto_error=False)


def get_job_by_access_token(
    creds: HTTPAuthorizationCredentials | None = None,
    token: str | None = None,
) -> dict:
    """
    按 access_token 查 jobs 表，返回任务行。
    token 可来自 Authorization: Bearer 头，也可来自 ?token= 查询参数。
    """
    raw = (creds.credentials if creds else None) or token
    if not raw:
        raise HTTPException(status_code=401, detail="缺少访问凭证（access_token）")
    res = get_db().table("jobs").select("*").eq("access_token", raw).execute()
    if not res.data:
        raise HTTPException(status_code=403, detail="无效或已过期的访问凭证")
    return res.data[0]


def _resolve_token(
    creds: HTTPAuthorizationCredentials | None,
    token: str | None,
) -> str | None:
    return (creds.credentials if creds else None) or token
