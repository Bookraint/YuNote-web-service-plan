"""SSE 任务进度队列（跨模块共享）"""
from __future__ import annotations

import queue
import threading

_queues: dict[str, queue.Queue] = {}
_lock = threading.Lock()


def get_queue(job_id: str) -> queue.Queue:
    with _lock:
        if job_id not in _queues:
            _queues[job_id] = queue.Queue(maxsize=512)
        return _queues[job_id]


def drop_queue(job_id: str) -> None:
    with _lock:
        _queues.pop(job_id, None)
