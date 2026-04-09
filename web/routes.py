"""FastAPI 路由定义（无用户账号，access_token 凭证访问）"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import queue
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.entities import NoteSceneEnum
from core.utils.audio_utils import get_duration

from . import settings as cfg
from .deps import get_job_by_access_token
from .cancel_registry import request_cancel
from .job_queue import drop_queue, get_queue
from .job_store import JobStore

router = APIRouter()

_PROMPT_FILES: dict[str, str] = {
    "general":   "summary_general.md",
    "meeting":   "summary_meeting.md",
    "lecture":   "summary_lecture.md",
    "interview": "summary_interview.md",
}

_SCENE_MAP: dict[str, NoteSceneEnum] = {
    "通用": NoteSceneEnum.GENERAL,
    "会议": NoteSceneEnum.MEETING,
    "课程": NoteSceneEnum.LECTURE,
    "访谈": NoteSceneEnum.INTERVIEW,
}


# ── 场景 Prompt（读文件系统，无 per-user 存储）───────────────────

class PromptsBody(BaseModel):
    general:   str = Field(default="")
    meeting:   str = Field(default="")
    lecture:   str = Field(default="")
    interview: str = Field(default="")


@router.get("/api/prompts")
def get_prompts():
    out: dict[str, str] = {}
    for key, fname in _PROMPT_FILES.items():
        path = cfg.PROMPTS_DIR / fname
        out[key] = path.read_text(encoding="utf-8") if path.exists() else ""
    return out


# ── 上传文件并获取报价 ────────────────────────────────────────────

@router.post("/api/jobs")
async def create_job(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form(default=""),
    scene: str = Form(default="通用"),
):
    store: JobStore = request.app.state.store

    content = await file.read()
    if len(content) > cfg.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, detail=f"文件超过 {cfg.MAX_UPLOAD_MB} MB 限制")

    suffix  = Path(file.filename or "audio").suffix or ".mp3"
    job_id  = uuid.uuid4().hex[:12]
    stem    = Path(file.filename or "audio").stem[:40]
    note_id = f"{stem}_{job_id}"

    upload_dir = cfg.UPLOAD_DIR / job_id
    audio_path = upload_dir / f"{job_id}{suffix}"

    def _save_file() -> None:
        upload_dir.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(content)

    await asyncio.to_thread(_save_file)

    duration_sec   = await asyncio.to_thread(get_duration, str(audio_path))
    billed_minutes = max(1, math.ceil(duration_sec / 60)) if duration_sec else 1

    await asyncio.to_thread(
        store.create,
        job_id=job_id,
        note_id=note_id,
        filename=file.filename or "",
        tier="standard",
        scene=scene,
        language=language,
        upload_file_path=str(audio_path),
        duration_sec=duration_sec,
    )

    return JSONResponse({
        "job_id":                   job_id,
        "note_id":                  note_id,
        "status":                   "awaiting_payment",
        "duration_sec":             duration_sec,
        "billed_minutes":           billed_minutes,
        "credits_standard":         billed_minutes * cfg.PRICE_PER_MIN_STANDARD_CREDITS,
        "credits_premium":          billed_minutes * cfg.PRICE_PER_MIN_PREMIUM_CREDITS,
    }, status_code=201)


# ── 查询任务状态（仅凭 job_id，支付前用）────────────────────────

@router.get("/api/jobs/{job_id}/status")
def get_job_status(job_id: str, request: Request):
    """支付前轮询用，只返回 status/progress/stage，不含结果路径。"""
    job = request.app.state.store.get(job_id)
    if not job:
        raise HTTPException(404, detail="任务不存在")
    return {
        "job_id":   job["job_id"],
        "status":   job["status"],
        "progress": job["progress"],
        "stage":    job["stage"],
        "error":    job.get("error"),
    }


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request):
    store: JobStore = request.app.state.store
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, detail="任务不存在")
    st = job.get("status") or ""
    if st in ("done", "failed", "cancelled"):
        return {"ok": True, "status": st}
    fired = request_cancel(job_id)
    if not fired and st == "awaiting_payment":
        store.update(job_id, status="cancelled", stage="已取消", error="")
        return {"ok": True}
    if fired and st in ("queued", "transcribing", "summarizing", "awaiting_payment"):
        try:
            store.update(job_id, stage="正在停止…")
        except Exception:
            # 取消信号已发出，stage 更新失败不影响结果
            logger.warning("cancel_job: 更新 stage 失败 job_id=%s", job_id)
    return {"ok": True}


# ── SSE 进度流（支付前/后均可用，只需 job_id）────────────────────

@router.get("/api/jobs/{job_id}/stream")
async def stream_progress(job_id: str, request: Request):
    store: JobStore = request.app.state.store
    job = await asyncio.to_thread(store.get, job_id)
    if not job:
        raise HTTPException(404, detail="任务不存在")

    prog_queue = get_queue(job_id)

    async def _event_gen():
        try:
            while True:
                drained_any = False
                while True:
                    try:
                        item = prog_queue.get_nowait()
                        drained_any = True
                        data = json.dumps(item, ensure_ascii=False)
                        yield f"data: {data}\n\n"
                        if item.get("__end__"):
                            return
                    except queue.Empty:
                        break

                if not drained_any:
                    j = await asyncio.to_thread(store.get, job_id)
                    if j and j["status"] in ("done", "failed", "cancelled"):
                        yield (
                            f"data: {json.dumps({'__end__': True, 'status': j['status'], 'progress': j['progress'], 'stage': j['stage']}, ensure_ascii=False)}\n\n"
                        )
                        return
                    yield ": keepalive\n\n"

                await asyncio.sleep(0.4)
        finally:
            drop_queue(job_id)

    return StreamingResponse(
        _event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── 获取结果（凭 access_token 查询参数）─────────────────────────

def _note_dir(job: dict) -> Path:
    return cfg.NOTES_DIR / job["note_id"]


def _require_job(job_id: str, token: str | None) -> dict:
    """按 access_token 查 job，并校验 job_id 匹配。"""
    job = get_job_by_access_token(None, token)
    if job["job_id"] != job_id:
        raise HTTPException(403, detail="凭证与任务不匹配")
    return job


@router.get("/api/jobs/{job_id}/transcript")
def get_transcript(
    job_id: str,
    token: str | None = Query(default=None),
):
    job = _require_job(job_id, token)
    base = _note_dir(job)
    path = base / "transcript.txt"
    if not path.exists():
        raise HTTPException(404, detail="转录文件尚未生成")
    text = path.read_text(encoding="utf-8")
    seg_path = base / "transcript_segments.json"
    segments: Optional[list] = None
    if seg_path.exists():
        try:
            segments = json.loads(seg_path.read_text(encoding="utf-8"))
        except Exception:
            segments = None
    return {"text": text, "segments": segments}


@router.get("/api/jobs/{job_id}/summary")
def get_summary(
    job_id: str,
    token: str | None = Query(default=None),
):
    job = _require_job(job_id, token)
    path = _note_dir(job) / "summary.md"
    if not path.exists():
        raise HTTPException(404, detail="总结文件尚未生成")
    return {"markdown": path.read_text(encoding="utf-8")}


@router.get("/api/jobs/{job_id}/transcript/download")
def download_transcript(
    job_id: str,
    token: str | None = Query(default=None),
):
    job = _require_job(job_id, token)
    path = _note_dir(job) / "transcript.txt"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, filename=f"{job_id}_transcript.txt", media_type="text/plain; charset=utf-8")


@router.get("/api/jobs/{job_id}/summary/download")
def download_summary(
    job_id: str,
    token: str | None = Query(default=None),
):
    job = _require_job(job_id, token)
    path = _note_dir(job) / "summary.md"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, filename=f"{job_id}_summary.md", media_type="text/markdown; charset=utf-8")
