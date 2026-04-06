"""Supabase 客户端单例"""
from __future__ import annotations

from supabase import Client, create_client

from . import settings as cfg

_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        if not cfg.SUPABASE_URL or not cfg.SUPABASE_SERVICE_KEY:
            raise RuntimeError(
                "SUPABASE_URL 和 SUPABASE_SERVICE_KEY 环境变量未配置"
            )
        _client = create_client(cfg.SUPABASE_URL, cfg.SUPABASE_SERVICE_KEY)
    return _client
