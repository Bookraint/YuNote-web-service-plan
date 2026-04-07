"""
服务端配置——从环境变量读取。
"""
from __future__ import annotations

import os
import re
from pathlib import Path


def _env_str(key: str, default: str = "") -> str:
    raw = os.environ.get(key, default).strip()
    if raw.startswith("#"):
        return ""
    if " #" in raw:
        raw = raw.split(" #")[0].strip()
    return raw


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


from core.entities import (
    LLMServiceEnum,
    NoteSceneEnum,
    SummaryConfig,
    TranscribeConfig,
    TranscribeModelEnum,
)

# ── Supabase ──────────────────────────────────────────────────────
SUPABASE_URL         = _env_str("SUPABASE_URL")
SUPABASE_SERVICE_KEY = _env_str("SUPABASE_SERVICE_KEY")

# ── 兑换码积分定价（积分/分钟）────────────────────────────────────
# 标准档：默认 10 积分/分钟；高级档：默认 30 积分/分钟
PRICE_PER_MIN_STANDARD_CREDITS = int(os.environ.get("PRICE_PER_MIN_STANDARD_CREDITS", "10"))
PRICE_PER_MIN_PREMIUM_CREDITS  = int(os.environ.get("PRICE_PER_MIN_PREMIUM_CREDITS",  "30"))

# ── 开发/测试模式：跳过兑换码验证直接激活 ─────────────────────────
# 设为 true 时任意输入的兑换码均视为有效（用于本地调试）
DEV_SKIP_REDEEM = _env_bool("DEV_SKIP_REDEEM", False)

# ── 管理后台密钥（生成兑换码接口）──────────────────────────────────
# 用于 POST /api/admin/codes，请设置为足够随机的长字符串
ADMIN_KEY = _env_str("ADMIN_KEY")

# ── LLM ──────────────────────────────────────────────────────────
LLM_BASE_URL      = os.environ.get("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_API_KEY       = os.environ.get("LLM_API_KEY", "")
LLM_MODEL         = os.environ.get("LLM_MODEL",   "qwen-plus")
LLM_MODEL_PREMIUM = os.environ.get("LLM_MODEL_PREMIUM", "qwen-max")
# 单次总结 LLM 请求超时（秒）；过小易中断长文本，过大则「卡住」体感明显
LLM_REQUEST_TIMEOUT_SEC = float(os.environ.get("LLM_REQUEST_TIMEOUT_SEC", "600"))

# ── ElevenLabs ───────────────────────────────────────────────────
ELEVENLABS_MODEL_ID         = os.environ.get("ELEVENLABS_MODEL_ID",         "scribe_v1")
ELEVENLABS_DIARIZE          = os.environ.get("ELEVENLABS_DIARIZE",          "true").lower() == "true"
ELEVENLABS_TAG_AUDIO_EVENTS = os.environ.get("ELEVENLABS_TAG_AUDIO_EVENTS", "false").lower() == "true"

# ── 转录参数 ─────────────────────────────────────────────────────
TRANSCRIBE_LANGUAGE                = _env_str("TRANSCRIBE_LANGUAGE")
TRANSCRIBE_CHUNK_LENGTH_MINUTES    = int(os.environ.get("TRANSCRIBE_CHUNK_LENGTH_MINUTES",    "15"))
TRANSCRIBE_SPLIT_THRESHOLD_MINUTES = int(os.environ.get("TRANSCRIBE_SPLIT_THRESHOLD_MINUTES", "25"))
TRANSCRIBE_RATE_LIMIT_PER_MINUTE   = int(os.environ.get("TRANSCRIBE_RATE_LIMIT_PER_MINUTE",   "10"))
TRANSCRIBE_MAX_CONCURRENT_CHUNKS   = int(os.environ.get("TRANSCRIBE_MAX_CONCURRENT_CHUNKS",   "3"))
TRANSCRIBE_CHUNK_MAX_RETRIES       = int(os.environ.get("TRANSCRIBE_CHUNK_MAX_RETRIES",       "3"))

# ── 总结参数 ─────────────────────────────────────────────────────
SUMMARY_CHUNK_SIZE      = int(os.environ.get("SUMMARY_CHUNK_SIZE",      "4093"))
SUMMARY_MAP_CONCURRENCY = int(os.environ.get("SUMMARY_MAP_CONCURRENCY", "5"))
SUMMARY_MAP_RPM         = int(os.environ.get("SUMMARY_MAP_RPM",         "30"))

# ── 存储路径 ─────────────────────────────────────────────────────
_root = Path(__file__).parent.parent
_pd = _env_str("PROMPTS_DIR", "")
if _pd:
    _p = Path(_pd).expanduser()
    PROMPTS_DIR = _p.resolve() if _p.is_absolute() else (_root / _p).resolve()
else:
    PROMPTS_DIR = (_root / "prompts").resolve()

NOTES_DIR  = Path(os.environ.get("NOTES_DIR",  str(_root / "data" / "notes")))
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(_root / "data" / "uploads")))

# ── 服务器 ───────────────────────────────────────────────────────
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "500"))
CORS_ORIGINS  = _env_str("CORS_ORIGINS", "*").split(",")


# ── 工厂方法 ─────────────────────────────────────────────────────

def make_transcribe_config(language: str = "") -> TranscribeConfig:
    return TranscribeConfig(
        transcribe_model=TranscribeModelEnum.ELEVENLABS,
        transcribe_language=language or TRANSCRIBE_LANGUAGE,
        need_word_time_stamp=False,
        elevenlabs_model_id=ELEVENLABS_MODEL_ID,
        elevenlabs_diarize=ELEVENLABS_DIARIZE,
        elevenlabs_tag_audio_events=ELEVENLABS_TAG_AUDIO_EVENTS,
        transcribe_enable_async=True,
        transcribe_max_concurrent_chunks=TRANSCRIBE_MAX_CONCURRENT_CHUNKS,
        transcribe_chunk_max_retries=TRANSCRIBE_CHUNK_MAX_RETRIES,
        transcribe_api_rate_limit_per_minute=TRANSCRIBE_RATE_LIMIT_PER_MINUTE,
        transcribe_split_threshold_minutes=TRANSCRIBE_SPLIT_THRESHOLD_MINUTES,
        transcribe_chunk_length_minutes=TRANSCRIBE_CHUNK_LENGTH_MINUTES,
    )


def make_summary_config(
    scene: NoteSceneEnum = NoteSceneEnum.GENERAL,
    tier: str = "standard",
    user_prompts: dict | None = None,
) -> SummaryConfig:
    prompts = user_prompts or {}
    llm_model = LLM_MODEL_PREMIUM if tier == "premium" else LLM_MODEL
    return SummaryConfig(
        scene=scene,
        llm_service=LLMServiceEnum.OPENAI,
        llm_base_url=LLM_BASE_URL,
        llm_api_key=LLM_API_KEY,
        llm_model=llm_model,
        chunk_size=SUMMARY_CHUNK_SIZE,
        map_concurrency=SUMMARY_MAP_CONCURRENCY,
        map_rpm=SUMMARY_MAP_RPM,
        prompts_path=str(PROMPTS_DIR),
        prompt_template_general=prompts.get("general", ""),
        prompt_template_meeting=prompts.get("meeting", ""),
        prompt_template_lecture=prompts.get("lecture", ""),
        prompt_template_interview=prompts.get("interview", ""),
        llm_timeout_sec=LLM_REQUEST_TIMEOUT_SEC,
    )
