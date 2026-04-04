"""ElevenLabs 专用转录入口（精简版，去除 FasterWhisper/WhisperCPP 等桌面依赖）"""
from __future__ import annotations

from typing import Callable, Optional

from core.asr.asr_data import ASRData
from core.asr.chunked_asr import ChunkedASR
from core.asr.elevenlabs import ElevenLabsASR
from core.entities import TranscribeConfig


def transcribe(
    audio_path: str,
    config: TranscribeConfig,
    callback: Optional[Callable[[int, str], None]] = None,
) -> ASRData:
    chunk_sec = max(60, config.transcribe_chunk_length_minutes * 60)
    conc = max(1, config.transcribe_max_concurrent_chunks)
    if not config.transcribe_enable_async:
        conc = 1

    asr_kwargs = {
        "use_cache": True,
        "need_word_time_stamp": config.need_word_time_stamp,
        "language": config.transcribe_language,
        "model_id": config.elevenlabs_model_id or "scribe_v1",
        "diarize": config.elevenlabs_diarize,
        "tag_audio_events": config.elevenlabs_tag_audio_events,
    }

    chunked = ChunkedASR(
        asr_class=ElevenLabsASR,
        audio_path=audio_path,
        asr_kwargs=asr_kwargs,
        chunk_length=chunk_sec,
        chunk_concurrency=conc,
        enable_async=config.transcribe_enable_async,
        max_retries=max(1, config.transcribe_chunk_max_retries),
        rate_limit_per_minute=max(0, config.transcribe_api_rate_limit_per_minute),
        split_threshold_minutes=config.transcribe_split_threshold_minutes,
    )

    asr_data = chunked.run(callback=callback)
    if not config.need_word_time_stamp:
        asr_data.optimize_timing()
    return asr_data
