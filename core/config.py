"""
Web 服务的路径与日志配置（替代桌面端 app/config.py，无 Qt 依赖）。
所有路径以本文件为锚点向上推算，数据落在 data/ 目录。
"""
import logging
from pathlib import Path

# YuNote-web-service-plan/
ROOT_PATH   = Path(__file__).parent.parent
DATA_PATH   = ROOT_PATH / "data"
LOG_PATH    = DATA_PATH / "logs"
CACHE_PATH  = DATA_PATH / "cache"

LOG_LEVEL  = logging.INFO
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# 确保目录存在
for _p in [LOG_PATH, CACHE_PATH]:
    _p.mkdir(parents=True, exist_ok=True)
