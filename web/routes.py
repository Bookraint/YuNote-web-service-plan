"""FastAPI 路由定义"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.entities import NoteSceneEnum

from . import settings as cfg
from .pipeline import run_pipeline

router = APIRouter()

# 场景 Prompt 文件名（与 core/summary/summarizer._SCENE_PROMPT_FILES 一致）
_PROMPT_FILES: dict[str, str] = {
    "general": "summary_general.md",
    "meeting": "summary_meeting.md",
    "lecture": "summary_lecture.md",
    "interview": "summary_interview.md",
}


class PromptsBody(BaseModel):
    general: str = Field(default="", description="通用场景 Markdown，须含 {{transcript}}")
    meeting: str = Field(default="", description="会议")
    lecture: str = Field(default="", description="课程")
    interview: str = Field(default="", description="访谈")


# ── 场景 Prompt（网页随改，写入 PROMPTS_DIR）──────────────────────────

@router.get("/api/prompts")
def get_prompts():
    """读取当前四套场景模板（磁盘上的最新内容，下次总结立即生效）。"""
    out: dict[str, str] = {}
    for key, fname in _PROMPT_FILES.items():
        path = cfg.PROMPTS_DIR / fname
        out[key] = path.read_text(encoding="utf-8") if path.exists() else ""
    out["prompts_dir"] = str(cfg.PROMPTS_DIR)
    return out


@router.put("/api/prompts")
def put_prompts(body: PromptsBody):
    """保存四套场景模板；每份须包含占位符 {{transcript}}。"""
    data = {
        "general": body.general,
        "meeting": body.meeting,
        "lecture": body.lecture,
        "interview": body.interview,
    }
    for key, text in data.items():
        if "{{transcript}}" not in text:
            raise HTTPException(
                400,
                detail=f"场景「{key}」模板必须包含占位符 {{transcript}}",
            )
    cfg.PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    for key, fname in _PROMPT_FILES.items():
        (cfg.PROMPTS_DIR / fname).write_text(data[key], encoding="utf-8")
    return {"ok": True, "prompts_dir": str(cfg.PROMPTS_DIR)}


# 每个任务对应一个进度队列：progress_cb 从 worker 线程 put，SSE 端点 get
_progress_queues: dict[str, queue.Queue] = {}
_queues_lock = threading.Lock()


def _get_queue(job_id: str) -> queue.Queue:
    with _queues_lock:
        if job_id not in _progress_queues:
            _progress_queues[job_id] = queue.Queue(maxsize=512)
        return _progress_queues[job_id]


def _drop_queue(job_id: str) -> None:
    with _queues_lock:
        _progress_queues.pop(job_id, None)


# ── 上传并创建任务 ────────────────────────────────────────────────────

@router.post("/api/jobs")
async def create_job(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form(default=""),
    scene: str = Form(default="通用"),
):
    store = request.app.state.store

    content = await file.read()
    if len(content) > cfg.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, detail=f"文件超过 {cfg.MAX_UPLOAD_MB} MB 限制")

    suffix = Path(file.filename or "audio").suffix or ".mp3"
    job_id  = uuid.uuid4().hex[:12]
    stem    = Path(file.filename or "audio").stem[:40]
    note_id = f"{stem}_{job_id}"

    cfg.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    audio_path = cfg.UPLOAD_DIR / f"{job_id}{suffix}"
    audio_path.write_bytes(content)

    scene_map  = {s.value: s for s in NoteSceneEnum}
    scene_enum = scene_map.get(scene, NoteSceneEnum.GENERAL)
    note_dir   = cfg.NOTES_DIR / note_id

    store.create(job_id, note_id, file.filename or "", scene=scene, language=language)

    prog_queue = _get_queue(job_id)

    def _progress_cb(p: int, msg: str) -> None:
        try:
            prog_queue.put_nowait({"progress": p, "stage": msg})
        except queue.Full:
            pass

    def _worker() -> None:
        try:
            run_pipeline(
                job_id=job_id,
                audio_path=str(audio_path),
                note_dir=note_dir,
                scene=scene_enum,
                language=language,
                store=store,
                progress_cb=_progress_cb,
            )
        finally:
            # 发送终止信号（区别 done / failed）
            job = store.get(job_id)
            final_status = job["status"] if job else "failed"
            try:
                prog_queue.put_nowait({"__end__": True, "status": final_status})
            except queue.Full:
                pass

    threading.Thread(target=_worker, daemon=True).start()

    return JSONResponse({"job_id": job_id, "note_id": note_id, "status": "queued"}, status_code=201)


# ── 查询任务状态 ──────────────────────────────────────────────────────

@router.get("/api/jobs")
def list_jobs(request: Request):
    return request.app.state.store.list_all()


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    job = request.app.state.store.get(job_id)
    if not job:
        raise HTTPException(404, detail="任务不存在")
    return job


# ── SSE 进度流 ────────────────────────────────────────────────────────

@router.get("/api/jobs/{job_id}/stream")
async def stream_progress(job_id: str, request: Request):
    store = request.app.state.store
    if not store.get(job_id):
        raise HTTPException(404, detail="任务不存在")

    prog_queue = _get_queue(job_id)

    async def _event_gen():
        try:
            while True:
                # 先把队列里现有消息全部 drain
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

                # 没有新消息时，检查是否已是终态（防止队列漏掉终止信号）
                if not drained_any:
                    job = store.get(job_id)
                    if job and job["status"] in ("done", "failed"):
                        yield (
                            f"data: {json.dumps({'__end__': True, 'status': job['status'], 'progress': job['progress'], 'stage': job['stage']}, ensure_ascii=False)}\n\n"
                        )
                        return
                    # keepalive，防止微信/Nginx 断连
                    yield ": keepalive\n\n"

                await asyncio.sleep(0.4)
        finally:
            _drop_queue(job_id)

    return StreamingResponse(
        _event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # 关闭 Nginx 缓冲，让 SSE 实时到达
        },
    )


# ── 获取结果文本 ──────────────────────────────────────────────────────

def _note_dir(store, job_id: str) -> Path:
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, detail="任务不存在")
    return cfg.NOTES_DIR / job["note_id"]


@router.get("/api/jobs/{job_id}/transcript")
def get_transcript(job_id: str, request: Request):
    path = _note_dir(request.app.state.store, job_id) / "transcript.txt"
    if not path.exists():
        raise HTTPException(404, detail="转录文件尚未生成")
    return {"text": path.read_text(encoding="utf-8")}


@router.get("/api/jobs/{job_id}/summary")
def get_summary(job_id: str, request: Request):
    path = _note_dir(request.app.state.store, job_id) / "summary.md"
    if not path.exists():
        raise HTTPException(404, detail="总结文件尚未生成")
    return {"markdown": path.read_text(encoding="utf-8")}


# ── 下载文件 ──────────────────────────────────────────────────────────

@router.get("/api/jobs/{job_id}/transcript/download")
def download_transcript(job_id: str, request: Request):
    path = _note_dir(request.app.state.store, job_id) / "transcript.txt"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, filename=f"{job_id}_transcript.txt", media_type="text/plain; charset=utf-8")


@router.get("/api/jobs/{job_id}/summary/download")
def download_summary(job_id: str, request: Request):
    path = _note_dir(request.app.state.store, job_id) / "summary.md"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, filename=f"{job_id}_summary.md", media_type="text/markdown; charset=utf-8")
