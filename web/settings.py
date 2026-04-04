"""
服务端配置——从环境变量读取，替代桌面端 app.common.config.cfg（Qt 依赖）。
字段默认值与 YuNote/AppData/settings.json 中的本地配置一致。
完全独立，不引用 YuNote 目录。
"""
from __future__ import annotations

import os
from pathlib import Path


def _env_str(key: str, default: str = "") -> str:
    """读取环境变量字符串，自动去除行内注释和首尾空白。"""
    raw = os.environ.get(key, default).strip()
    # dotenv 某些版本不会自动去除行内注释（如 `VALUE= # comment`）
    if raw.startswith("#"):
        return ""
    if " #" in raw:
        raw = raw.split(" #")[0].strip()
    return raw

from core.entities import (
    LLMServiceEnum,
    NoteSceneEnum,
    SummaryConfig,
    TranscribeConfig,
    TranscribeModelEnum,
)

# ── LLM（OpenAI 兼容，默认对应本地 DashScope/Qwen 配置）────────────────
LLM_BASE_URL = os.environ.get(
    "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL   = os.environ.get("LLM_MODEL",   "qwen3.5-35b-a3b")

# ── ElevenLabs（对应本地 settings.json [ElevenLabs] 段）───────────────
ELEVENLABS_MODEL_ID         = os.environ.get("ELEVENLABS_MODEL_ID",         "scribe_v1")
ELEVENLABS_DIARIZE          = os.environ.get("ELEVENLABS_DIARIZE",          "true").lower() == "true"
ELEVENLABS_TAG_AUDIO_EVENTS = os.environ.get("ELEVENLABS_TAG_AUDIO_EVENTS", "false").lower() == "true"

# ── 转录参数（对应本地 settings.json [Transcribe] 段）─────────────────
TRANSCRIBE_LANGUAGE                = _env_str("TRANSCRIBE_LANGUAGE")
TRANSCRIBE_CHUNK_LENGTH_MINUTES    = int(os.environ.get("TRANSCRIBE_CHUNK_LENGTH_MINUTES",    "15"))
TRANSCRIBE_SPLIT_THRESHOLD_MINUTES = int(os.environ.get("TRANSCRIBE_SPLIT_THRESHOLD_MINUTES", "25"))
TRANSCRIBE_RATE_LIMIT_PER_MINUTE   = int(os.environ.get("TRANSCRIBE_RATE_LIMIT_PER_MINUTE",   "10"))
TRANSCRIBE_MAX_CONCURRENT_CHUNKS   = int(os.environ.get("TRANSCRIBE_MAX_CONCURRENT_CHUNKS",   "3"))
TRANSCRIBE_CHUNK_MAX_RETRIES       = int(os.environ.get("TRANSCRIBE_CHUNK_MAX_RETRIES",       "3"))

# ── 总结参数（Map-Reduce 分块与限流）──────────────────────────────────
SUMMARY_CHUNK_SIZE      = int(os.environ.get("SUMMARY_CHUNK_SIZE",       "4093"))
SUMMARY_MAP_CONCURRENCY = int(os.environ.get("SUMMARY_MAP_CONCURRENCY",  "5"))
SUMMARY_MAP_RPM         = int(os.environ.get("SUMMARY_MAP_RPM",          "30"))

# ── 存储路径 ─────────────────────────────────────────────────────────
_root = Path(__file__).parent.parent
# 场景 Prompt 模板目录（默认项目内 prompts/；可改为绝对路径或相对项目根的路径）
_pd = _env_str("PROMPTS_DIR", "")
if _pd:
    _p = Path(_pd).expanduser()
    PROMPTS_DIR = _p.resolve() if _p.is_absolute() else (_root / _p).resolve()
else:
    PROMPTS_DIR = (_root / "prompts").resolve()

NOTES_DIR  = Path(os.environ.get("NOTES_DIR",  str(_root / "data" / "notes")))
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(_root / "data" / "uploads")))
DB_PATH    = Path(os.environ.get("DB_PATH",    str(_root / "data" / "jobs.db")))

# ── 服务器 ───────────────────────────────────────────────────────────
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "500"))
CORS_ORIGINS  = _env_str("CORS_ORIGINS", "*").split(",")


# ── 工厂方法：从环境变量组装配置对象 ─────────────────────────────────

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


def make_summary_config(scene: NoteSceneEnum = NoteSceneEnum.GENERAL) -> SummaryConfig:
    return SummaryConfig(
        scene=scene,
        llm_service=LLMServiceEnum.OPENAI,
        llm_base_url=LLM_BASE_URL,
        llm_api_key=LLM_API_KEY,
        llm_model=LLM_MODEL,
        chunk_size=SUMMARY_CHUNK_SIZE,
        map_concurrency=SUMMARY_MAP_CONCURRENCY,
        map_rpm=SUMMARY_MAP_RPM,
        prompts_path=str(PROMPTS_DIR),
    )
