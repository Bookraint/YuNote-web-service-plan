"""任务取消：与 runner 中的流水线线程共享 threading.Event。"""
from __future__ import annotations

import threading
from typing import Optional

_lock = threading.Lock()
_events: dict[str, threading.Event] = {}


def register_cancel_event(job_id: str) -> threading.Event:
    ev = threading.Event()
    with _lock:
        _events[job_id] = ev
    return ev


def unregister_cancel_event(job_id: str) -> None:
    with _lock:
        _events.pop(job_id, None)


def request_cancel(job_id: str) -> bool:
    """请求取消；若任务线程已注册则触发 Event。返回是否找到了可取消的任务。"""
    with _lock:
        ev = _events.get(job_id)
        if ev is not None:
            ev.set()
            return True
    return False


def get_cancel_event(job_id: str) -> Optional[threading.Event]:
    with _lock:
        return _events.get(job_id)
