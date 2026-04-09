"""
转录 → 总结 完整流水线，在独立线程中运行。
接受 user_prompts 和 tier 参数，以支持每用户自定义 Prompt 和不同档位 LLM。
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Callable, Optional

from core.asr.transcribe import transcribe
from core.entities import NoteSceneEnum
from core.summary.summarizer import Summarizer, SummarizerCancelledError
from core.utils.audio_utils import prepare_audio

from . import settings as cfg
from .job_store import JobStore

logger = logging.getLogger("web.pipeline")


class JobCancelledError(Exception):
    """用户通过「停止」请求中断任务。"""


def run_pipeline(
    job_id: str,
    audio_path: str,
    note_dir: Path,
    scene: NoteSceneEnum,
    language: str,
    store: JobStore,
    tier: str = "standard",
    user_prompts: Optional[dict] = None,
    progress_cb: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> None:
    """
    在后台线程执行完整的「转录 → 总结」流水线。
    每个阶段通过 store.update() 持久化进度，同时触发 progress_cb 推送 SSE。
    """

    def _cb(p: int, msg: str) -> None:
        store.update(job_id, progress=p, stage=msg)
        if progress_cb:
            progress_cb(p, msg)

    def _check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelledError()

    try:
        note_dir.mkdir(parents=True, exist_ok=True)

        # ── 阶段 1：转录 ────────────────────────────────────────────
        store.update(job_id, status="transcribing", progress=3, stage="预处理音频…")
        _check_cancel()

        processed_path = prepare_audio(audio_path, str(note_dir))
        if processed_path is None:
            raise RuntimeError(
                "不支持的音视频格式或转换失败，请上传 mp3 / m4a / mp4 / wav 等常见格式"
            )
        _cb(5, "语音转录中…")

        transcribe_cfg = cfg.make_transcribe_config(language=language)

        def _transcribe_cb(p: int, msg: str) -> None:
            _cb(int(5 + p * 0.45), msg)

        _asr_result: list = [None]
        _asr_error: list = [None]
        _asr_done = threading.Event()

        def _run_transcribe() -> None:
            try:
                _asr_result[0] = transcribe(processed_path, transcribe_cfg, callback=_transcribe_cb)
            except Exception as exc:
                _asr_error[0] = exc
            finally:
                _asr_done.set()

        t = threading.Thread(target=_run_transcribe, daemon=True)
        t.start()

        while not _asr_done.wait(timeout=0.5):
            _check_cancel()

        _check_cancel()
        if _asr_error[0] is not None:
            raise _asr_error[0]
        asr_data = _asr_result[0]

        transcript_text = (
            asr_data.to_txt(include_timestamps=True)
            if hasattr(asr_data, "to_txt")
            else str(asr_data)
        )
        (note_dir / "transcript.txt").write_text(transcript_text, encoding="utf-8")
        try:
            (note_dir / "transcript_segments.json").write_text(
                json.dumps(asr_data.ui_segments(), ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("写入 transcript_segments.json 失败 job_id=%s", job_id)
        asr_data.save(str(note_dir / "transcript.srt"))

        # 转录完成后立即删除中间 WAV 文件（由 prepare_audio 转换生成）。
        # 仅当 processed_path 与原始上传路径不同时才删，避免误删用户上传的 .wav 文件。
        if processed_path != audio_path:
            try:
                Path(processed_path).unlink(missing_ok=True)
                logger.debug("已删除转换后的临时 WAV job_id=%s path=%s", job_id, processed_path)
            except Exception:
                logger.warning("删除临时 WAV 失败 job_id=%s path=%s", job_id, processed_path)

        _cb(50, "转录完成，开始 AI 总结…")

        # ── 阶段 2：总结 ────────────────────────────────────────────
        _check_cancel()
        store.update(job_id, status="summarizing", progress=50, stage="AI 总结中…")

        summary_cfg = cfg.make_summary_config(
            scene=scene,
            tier=tier,
            user_prompts=user_prompts or {},
        )
        summarizer = Summarizer(summary_cfg)

        def _summary_cb(p: int, msg: str) -> None:
            _cb(int(50 + p * 0.5), msg)

        summary_md = summarizer.summarize(
            transcript_text,
            progress_callback=_summary_cb,
            cancel_event=cancel_event,
        )

        (note_dir / "summary.md").write_text(summary_md, encoding="utf-8")

        store.update(job_id, status="done", progress=100, stage="已完成")
        _cb(100, "已完成")

    except (JobCancelledError, SummarizerCancelledError):
        logger.info("任务已取消 job_id=%s", job_id)
        store.update(job_id, status="cancelled", progress=0, stage="已停止", error="")
        _cb(0, "已停止")
    except Exception as exc:
        logger.exception("Pipeline 失败 job_id=%s", job_id)
        err_msg = str(exc)[:500]
        store.update(job_id, status="failed", stage="处理失败", error=err_msg)
        if progress_cb:
            progress_cb(-1, f"失败：{err_msg}")
