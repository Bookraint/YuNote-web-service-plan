"""FastAPI 应用入口（无用户账号版）"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import settings as cfg
from .job_store import JobStore
from .routes import router
from .order_routes import router as order_router
from .admin_routes import router as admin_router

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg.NOTES_DIR.mkdir(parents=True, exist_ok=True)
    cfg.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    app.state.store = JobStore()
    yield


app = FastAPI(
    title="YuNote Web",
    version="0.3.0",
    description="音频转录与 AI 总结网页服务（一次付款，即用即得）",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(order_router)
app.include_router(admin_router)
app.include_router(router)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
