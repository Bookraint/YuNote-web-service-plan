"""在独立线程中启动流水线，供 order_routes 的 webhook 和开发模式调用。"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from core.entities import NoteSceneEnum

from . import settings as cfg
from .cancel_registry import register_cancel_event, unregister_cancel_event
from .job_queue import get_queue
from .job_store import JobStore
from .pipeline import run_pipeline

_SCENE_MAP: dict[str, NoteSceneEnum] = {
    "通用": NoteSceneEnum.GENERAL,
    "会议": NoteSceneEnum.MEETING,
    "课程": NoteSceneEnum.LECTURE,
    "访谈": NoteSceneEnum.INTERVIEW,
}


def start_job(
    job_id: str,
    audio_path: str,
    store: JobStore,
    user_prompts: Optional[dict] = None,
) -> None:
    """将 job 推入队列并在后台线程中运行流水线。"""
    job = store.get(job_id)
    if not job:
        return

    note_dir = cfg.NOTES_DIR / job["note_id"]
    scene = _SCENE_MAP.get(job.get("scene", "通用"), NoteSceneEnum.GENERAL)
    tier = job.get("tier", "standard")
    prog_queue = get_queue(job_id)
    cancel_ev = register_cancel_event(job_id)

    def _cb(p: int, msg: str) -> None:
        store.update(job_id, progress=p, stage=msg)
        try:
            prog_queue.put_nowait({"progress": p, "stage": msg})
        except Exception:
            pass

    def _worker() -> None:
        try:
            run_pipeline(
                job_id=job_id,
                audio_path=audio_path,
                note_dir=note_dir,
                scene=scene,
                language=job.get("language", ""),
                tier=tier,
                user_prompts=user_prompts or {},
                store=store,
                progress_cb=_cb,
                cancel_event=cancel_ev,
            )
        finally:
            unregister_cancel_event(job_id)
            j = store.get(job_id)
            final_status = j["status"] if j else "failed"
            try:
                prog_queue.put_nowait({"__end__": True, "status": final_status})
            except Exception:
                pass
            try:
                Path(audio_path).unlink(missing_ok=True)
            except Exception:
                pass

    store.update(job_id, status="queued", stage="队列等待中…")
    threading.Thread(target=_worker, daemon=True).start()
