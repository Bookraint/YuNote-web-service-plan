"""ElevenLabs Speech-to-Text（scribe_v1）云端转录。

使用查询参数 allow_unauthenticated=1 + 模拟官网浏览器请求头（与 scribe2srt 一致），不携带 API Key。
"""

from __future__ import annotations

import os
import random
from typing import Any, Callable, Dict, List, Optional, Union

import requests

from ..utils.logger import setup_logger
from .asr_data import ASRDataSeg
from .base import BaseASR

logger = setup_logger("elevenlabs_asr")

ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"

# 与 scribe2srt/api/client.py 对齐
ELEVENLABS_ALLOW_UNAUTH_PARAMS = {"allow_unauthenticated": "1"}
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
]
_ACCEPT_LANGUAGES = [
    "zh-CN,zh;q=0.9,en;q=0.8",
    "en-US,en;q=0.9,es;q=0.8",
    "ja-JP,ja;q=0.9,en;q=0.8",
    "ko-KR,ko;q=0.9,en;q=0.8",
]
_BROWSER_BASE_HEADERS: Dict[str, str] = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "origin": "https://elevenlabs.io",
    "referer": "https://elevenlabs.io/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}


class ElevenLabsASR(BaseASR):
    """ElevenLabs Scribe 云端 ASR，支持 diarize 说话人标注。"""

    def __init__(
        self,
        audio_input: Union[str, bytes],
        model_id: str = "scribe_v1",
        language: str = "",
        diarize: bool = True,
        tag_audio_events: bool = False,
        need_word_time_stamp: bool = False,
        use_cache: bool = True,
    ):
        super().__init__(audio_input, use_cache=use_cache)
        self.model_id = model_id or "scribe_v1"
        self.language = (language or "").strip()
        self.diarize = diarize
        self.tag_audio_events = tag_audio_events
        self.need_word_time_stamp = need_word_time_stamp

    def _browser_style_headers(self) -> Dict[str, str]:
        h = dict(_BROWSER_BASE_HEADERS)
        h["user-agent"] = random.choice(_USER_AGENTS)
        h["accept-language"] = random.choice(_ACCEPT_LANGUAGES)
        return h

    def _run(
        self,
        callback: Optional[Callable[[int, str], None]] = None,
        **kwargs: Any,
    ) -> dict:
        if callback:
            callback(20, "转录中…")

        path = self.audio_input if isinstance(self.audio_input, str) else ""
        basename = "audio.mp3"
        if path:
            basename = os.path.basename(path)

        mime = "application/octet-stream"
        if path:
            ext = os.path.splitext(path)[1].lower()
            _mime_map = {
                ".mp3": "audio/mpeg",
                ".wav": "audio/wav",
                ".m4a": "audio/mp4",
                ".flac": "audio/flac",
                ".ogg": "audio/ogg",
            }
            mime = _mime_map.get(ext, "application/octet-stream")

        files = {"file": (basename, self.file_binary or b"", mime)}
        data: dict[str, str] = {
            "model_id": self.model_id,
            "diarize": str(self.diarize).lower(),
            "tag_audio_events": str(self.tag_audio_events).lower(),
        }
        if self.language:
            data["language_code"] = self.language

        headers = self._browser_style_headers()
        params = ELEVENLABS_ALLOW_UNAUTH_PARAMS

        try:
            resp = requests.post(
                ELEVENLABS_STT_URL,
                files=files,
                data=data,
                headers=headers,
                params=params,
                timeout=1800,
            )
            resp.raise_for_status()
        except requests.HTTPError as e:
            body = ""
            if e.response is not None:
                try:
                    body = e.response.text[:500]
                except Exception:
                    body = ""
            logger.exception("ElevenLabs STT HTTP 错误: %s %s", e, body)
            raise RuntimeError(f"ElevenLabs 转录失败: {e}" + (f" | {body}" if body else "")) from e

        if callback:
            callback(100, "ElevenLabs 转录完成")

        return resp.json()

    def _merge_word_runs(self, words: list[dict]) -> List[dict]:
        """按时间顺序合并相邻、同说话人的词（含英文 spacing token）。"""
        sorted_words = sorted(words, key=lambda w: float(w.get("start", 0)))
        runs: List[dict] = []
        cur: Optional[dict] = None

        for w in sorted_words:
            t = w.get("type")
            if t == "audio_event":
                continue
            sid = str(w.get("speaker_id") or "")
            text = w.get("text") or ""
            st = int(float(w["start"]) * 1000)
            et = int(float(w["end"]) * 1000)

            if cur is not None and cur["speaker"] == sid:
                cur["text"] = cur["text"] + text
                cur["end"] = et
            else:
                if cur is not None:
                    runs.append(cur)
                cur = {"speaker": sid, "text": text, "start": st, "end": et}

        if cur is not None:
            runs.append(cur)
        return runs

    def _make_segments(self, resp_data: dict) -> List[ASRDataSeg]:
        words = resp_data.get("words")
        if not isinstance(words, list) or len(words) == 0:
            text = (resp_data.get("text") or "").strip()
            if not text:
                return []
            return [ASRDataSeg(text, 0, 0)]

        if self.need_word_time_stamp:
            segs: List[ASRDataSeg] = []
            for w in sorted(words, key=lambda x: float(x.get("start", 0))):
                if w.get("type") == "audio_event":
                    continue
                wt = w.get("text") or ""
                if w.get("type") == "spacing" and not wt.strip():
                    continue
                st = int(float(w["start"]) * 1000)
                et = int(float(w["end"]) * 1000)
                segs.append(ASRDataSeg(wt, st, et))
            return segs

        runs = self._merge_word_runs(words)
        out: List[ASRDataSeg] = []
        for r in runs:
            raw = (r["text"] or "").replace("\r", " ").strip()
            if not raw:
                continue
            if self.diarize and r.get("speaker"):
                display = f"[{r['speaker']}] {raw}"
            else:
                display = raw
            out.append(
                ASRDataSeg(display, r["start"], r["end"]),
            )
        return out

    def _get_key(self) -> str:
        return (
            f"{self.crc32_hex}-{self.model_id}-{self.language}-"
            f"{int(self.diarize)}-{int(self.tag_audio_events)}-"
            f"{int(self.need_word_time_stamp)}"
        )
