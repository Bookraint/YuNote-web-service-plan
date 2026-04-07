"""Supabase 客户端单例（带自动重连）"""
from __future__ import annotations

import logging

from supabase import Client, create_client

from . import settings as cfg

logger = logging.getLogger(__name__)

_client: Client | None = None


def _create() -> Client:
    if not cfg.SUPABASE_URL or not cfg.SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL 和 SUPABASE_SERVICE_KEY 环境变量未配置"
        )
    return create_client(cfg.SUPABASE_URL, cfg.SUPABASE_SERVICE_KEY)


def get_db() -> Client:
    global _client
    if _client is None:
        _client = _create()
    return _client


def reset_db() -> Client:
    """丢弃旧连接，创建新客户端（连接断开时调用）。"""
    global _client
    logger.warning("Supabase 连接已重置")
    _client = _create()
    return _client
