#!/usr/bin/env python3
"""
本地兑换码管理台（仅监听 127.0.0.1）。

从浏览器访问本机页面，通过服务端转发请求到 YuNote API，不在网页里暴露 ADMIN_KEY。

环境变量（可写入项目根目录 .env）：
  YUNOTE_API_BASE   线上或本地 API 根地址，无尾斜杠。例：https://xxx.hf.space 或 http://127.0.0.1:7860
  ADMIN_KEY         与主服务相同的管理员密钥

启动：
  cd YuNote-web-service-plan
  python scripts/redeem_admin_portal/run_portal.py

浏览器打开：http://127.0.0.1:8765
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx

API_BASE = os.environ.get("YUNOTE_API_BASE", "http://127.0.0.1:7860").rstrip("/")
ADMIN_KEY = (os.environ.get("ADMIN_KEY") or "").strip()

_STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="YuNote Redeem Admin (local)", version="1.0.0")


def _admin_headers() -> dict[str, str]:
    return {"X-Admin-Key": ADMIN_KEY}


def _forward_response(r: httpx.Response) -> JSONResponse:
    try:
        data = r.json()
    except Exception:
        data = {"detail": r.text[:2000] if r.text else "empty body"}
    return JSONResponse(content=data, status_code=r.status_code)


@app.get("/config")
def config():
    """给页面展示当前连接目标（不含密钥）。"""
    return {
        "api_base": API_BASE,
        "admin_configured": bool(ADMIN_KEY),
    }


@app.get("/api/stock")
def proxy_stock():
    if not ADMIN_KEY:
        raise HTTPException(503, detail="请在 .env 中配置 ADMIN_KEY")
    try:
        r = httpx.get(
            f"{API_BASE}/api/admin/codes/stock",
            headers=_admin_headers(),
            timeout=60.0,
        )
    except httpx.RequestError as e:
        raise HTTPException(502, detail=f"无法连接 {API_BASE}: {e}") from e
    return _forward_response(r)


@app.post("/api/codes/generate")
def proxy_generate(body: dict):
    if not ADMIN_KEY:
        raise HTTPException(503, detail="请在 .env 中配置 ADMIN_KEY")
    try:
        r = httpx.post(
            f"{API_BASE}/api/admin/codes",
            json=body,
            headers={**_admin_headers(), "Content-Type": "application/json"},
            timeout=120.0,
        )
    except httpx.RequestError as e:
        raise HTTPException(502, detail=f"无法连接 {API_BASE}: {e}") from e
    return _forward_response(r)


@app.get("/api/codes/list")
def proxy_list(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    if not ADMIN_KEY:
        raise HTTPException(503, detail="请在 .env 中配置 ADMIN_KEY")
    params: dict = {"limit": limit, "offset": offset}
    if status in ("unused", "used"):
        params["status"] = status
    try:
        r = httpx.get(
            f"{API_BASE}/api/admin/codes",
            params=params,
            headers=_admin_headers(),
            timeout=60.0,
        )
    except httpx.RequestError as e:
        raise HTTPException(502, detail=f"无法连接 {API_BASE}: {e}") from e
    return _forward_response(r)


@app.post("/api/codes/void")
def proxy_void(body: dict):
    if not ADMIN_KEY:
        raise HTTPException(503, detail="请在 .env 中配置 ADMIN_KEY")
    try:
        r = httpx.post(
            f"{API_BASE}/api/admin/codes/void",
            json=body,
            headers={**_admin_headers(), "Content-Type": "application/json"},
            timeout=60.0,
        )
    except httpx.RequestError as e:
        raise HTTPException(502, detail=f"无法连接 {API_BASE}: {e}") from e
    return _forward_response(r)


@app.get("/")
def index():
    index_path = _STATIC / "index.html"
    if not index_path.is_file():
        raise HTTPException(500, detail=f"缺少静态文件: {index_path}")
    return FileResponse(index_path)


if _STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


def main() -> None:
    if not ADMIN_KEY:
        print(
            "警告：未设置 ADMIN_KEY，页面将无法调用远端。请在 .env 中配置。\n",
            file=sys.stderr,
        )
    import uvicorn

    host = os.environ.get("REDEEM_ADMIN_HOST", "127.0.0.1")
    port = int(os.environ.get("REDEEM_ADMIN_PORT", "8765"))
    print(f"兑换码管理台: http://{host}:{port}")
    print(f"转发目标 API: {API_BASE}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
