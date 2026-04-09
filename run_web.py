#!/usr/bin/env python3
"""
YuNote Web 服务启动入口

使用方式：
    cp .env.example .env        # 填入 API Keys
    uv sync                     # 或：pip install -r requirements-web.txt
    python run_web.py           # 开发模式（热重载）

生产环境：
    uvicorn web.main:app --host 0.0.0.0 --port 8000 --workers 2
"""
import sys
import uvicorn

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run(
        "web.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_dirs=["web"],
        log_level="info",
    )
