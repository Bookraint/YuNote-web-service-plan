"""
转录 → 总结 完整流水线，在独立线程中运行。
直接调用 core/ 下的 transcribe() 与 Summarizer，不依赖 YuNote 原仓库。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from core.asr.transcribe import transcribe
from core.entities import NoteSceneEnum
from core.summary.summarizer import Summarizer
from core.utils.audio_utils import prepare_audio

from . import settings as cfg
from .job_store import JobStore

logger = logging.getLogger("web.pipeline")


def run_pipeline(
    job_id: str,
    audio_path: str,
    note_dir: Path,
    scene: NoteSceneEnum,
    language: str,
    store: JobStore,
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> None:
    """
    在后台线程执行完整的「转录 → 总结」流水线。
    每个阶段通过 store.update() 持久化进度，同时触发 progress_cb 推送 SSE。
    """

    def _cb(p: int, msg: str) -> None:
        store.update(job_id, progress=p, stage=msg)
        if progress_cb:
            progress_cb(p, msg)

    try:
        note_dir.mkdir(parents=True, exist_ok=True)

        # ── 阶段 1：转录 ────────────────────────────────────────────
        store.update(job_id, status="transcribing", progress=3, stage="预处理音频…")

        # mp4/mkv 等视频格式先提取音轨，不支持的格式直接报错
        processed_path = prepare_audio(audio_path, str(note_dir))
        if processed_path is None:
            raise RuntimeError(
                f"不支持的音视频格式或转换失败，请上传 mp3 / m4a / mp4 / wav 等常见格式"
            )
        _cb(5, "语音转录中…")

        transcribe_cfg = cfg.make_transcribe_config(language=language)

        # 转录进度占总进度 5% → 50%
        def _transcribe_cb(p: int, msg: str) -> None:
            mapped = int(5 + p * 0.45)
            _cb(mapped, msg)

        asr_data = transcribe(processed_path, transcribe_cfg, callback=_transcribe_cb)

        transcript_text = (
            asr_data.to_txt(include_timestamps=True)
            if hasattr(asr_data, "to_txt")
            else str(asr_data)
        )
        (note_dir / "transcript.txt").write_text(transcript_text, encoding="utf-8")
        asr_data.save(str(note_dir / "transcript.srt"))

        _cb(50, "转录完成，开始 AI 总结…")

        # ── 阶段 2：总结 ────────────────────────────────────────────
        store.update(job_id, status="summarizing", progress=50, stage="AI 总结中…")

        summary_cfg = cfg.make_summary_config(scene=scene)
        summarizer = Summarizer(summary_cfg)

        # 总结进度占总进度 50% → 100%
        def _summary_cb(p: int, msg: str) -> None:
            mapped = int(50 + p * 0.5)
            _cb(mapped, msg)

        summary_md = summarizer.summarize(transcript_text, progress_callback=_summary_cb)

        (note_dir / "summary.md").write_text(summary_md, encoding="utf-8")

        store.update(job_id, status="done", progress=100, stage="已完成")
        _cb(100, "已完成")

    except Exception as exc:
        logger.exception("Pipeline 失败 job_id=%s", job_id)
        err_msg = str(exc)[:500]
        store.update(job_id, status="failed", stage="处理失败", error=err_msg)
        if progress_cb:
            progress_cb(-1, f"失败：{err_msg}")
