"""
Map-Reduce 两阶段总结。

阶段一（Map）：将长转录文本分块，每块独立生成摘要；可按配置并发请求，并受 RPM 限制。
阶段二（Reduce）：将所有块摘要合并，再次调用 LLM 生成最终结构化笔记。

若文本较短（< chunk_size），直接单次完成。
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, List, Optional, cast

from openai import OpenAI

from core.entities import NoteSceneEnum, SummaryConfig
from core.summary.chunker import split_into_chunks
from core.utils.logger import setup_logger

logger = setup_logger("summarizer")

_SCENE_PROMPT_FILES = {
    NoteSceneEnum.MEETING:   "summary_meeting.md",
    NoteSceneEnum.LECTURE:   "summary_lecture.md",
    NoteSceneEnum.INTERVIEW: "summary_interview.md",
    NoteSceneEnum.GENERAL:   "summary_general.md",
}

_MAP_SYSTEM = (
    "你是内容整理助手。请对下面这段转录片段进行要点提取，"
    "输出简洁的条目式摘要，保留关键信息，过滤口头禅和重复内容。"
)


class Summarizer:

    def __init__(self, config: SummaryConfig):
        self.config = config
        self._client = OpenAI(
            api_key=config.llm_api_key or "sk-placeholder",
            base_url=config.llm_base_url or None,
        )

    def summarize(
        self,
        transcript: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> str:
        """
        执行完整总结流程。

        Args:
            transcript: 转录原文
            progress_callback: (progress 0-100, status_text) 回调

        Returns:
            Markdown 格式的总结文本
        """
        def _cb(p: int, msg: str):
            if progress_callback:
                progress_callback(p, msg)

        chunks = split_into_chunks(transcript, self.config.chunk_size)
        logger.info("分块数量: %d，总字符: %d", len(chunks), len(transcript))

        if len(chunks) == 1:
            _cb(10, "生成总结中…")
            result = self._single_pass(transcript)
            _cb(100, "总结完成")
            return result

        # Map 阶段（可并发 + RPM）
        chunk_summaries = self._map_chunks_parallel(chunks, _cb)

        # Reduce 阶段
        _cb(75, "整合生成最终总结…")
        merged = "\n\n".join(
            f"【片段 {i + 1} 摘要】\n{s}" for i, s in enumerate(chunk_summaries)
        )
        result = self._reduce(merged)
        _cb(100, "总结完成")
        return result

    def _map_chunks_parallel(
        self,
        chunks: List[str],
        _cb: Callable[[int, str], None],
    ) -> List[str]:
        """Map 阶段：顺序或线程池并发，共享 RPM 滑动窗口。"""
        n = len(chunks)
        workers = max(1, min(self.config.map_concurrency, n))
        rpm_times: List[float] = []
        rpm_lock = threading.Lock()
        progress_lock = threading.Lock()
        completed = 0

        def wait_rpm() -> None:
            limit = self.config.map_rpm
            if limit <= 0:
                return
            window = 60.0
            while True:
                with rpm_lock:
                    now = time.time()
                    rpm_times[:] = [t for t in rpm_times if now - t < window]
                    if len(rpm_times) < limit:
                        rpm_times.append(time.time())
                        return
                    wait = window - (now - rpm_times[0])
                if wait > 0:
                    time.sleep(wait)
                else:
                    time.sleep(0.05)

        def map_one(idx: int, chunk: str) -> tuple[int, str]:
            wait_rpm()
            summary = self._map_chunk(chunk)
            nonlocal completed
            with progress_lock:
                completed += 1
                pct = int(10 + (completed / n) * 60)
                _cb(pct, f"分析片段 {completed}/{n}…")
            return idx, summary

        if workers == 1:
            ordered: List[str] = []
            for i, ch in enumerate(chunks):
                _, s = map_one(i, ch)
                ordered.append(s)
                logger.debug("片段 %d 摘要长度: %d", i + 1, len(s))
            return ordered

        slot: List[Optional[str]] = [None] * n
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(map_one, i, c): i for i, c in enumerate(chunks)}
            for fut in as_completed(futures):
                idx, summary = fut.result()
                slot[idx] = summary
                logger.debug("片段 %d 摘要长度: %d", idx + 1, len(summary))

        return cast(List[str], slot)

    def _single_pass(self, text: str) -> str:
        """文本较短时直接单次生成。"""
        prompt = self._build_final_prompt(text)
        return self._call_llm(system=self._get_system_prompt(), user=prompt)

    def _map_chunk(self, chunk: str) -> str:
        """对单个分块生成摘要。"""
        return self._call_llm(
            system=_MAP_SYSTEM,
            user=f"转录片段：\n\n{chunk}",
        )

    def _reduce(self, merged_summaries: str) -> str:
        """将所有块摘要汇总，生成最终结构化笔记。"""
        prompt = self._build_final_prompt(merged_summaries)
        return self._call_llm(system=self._get_system_prompt(), user=prompt)

    def _call_llm(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self.config.llm_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content or ""

    def _get_system_prompt(self) -> str:
        return "你是专业的笔记整理助手，擅长将音频转录内容整理为结构清晰的 Markdown 笔记。"

    def _build_final_prompt(self, content: str) -> str:
        """将内容注入场景 Prompt 模板。"""
        template = self._load_prompt_template()
        return template.replace("{{transcript}}", content)

    def _load_prompt_template(self) -> str:
        """从 resource/prompts/ 加载对应场景的模板文件。"""
        filename = _SCENE_PROMPT_FILES.get(self.config.scene, "summary_general.md")
        template_path = Path(self.config.prompts_path) / filename

        # 如果用户在设置里覆盖了“场景模板”，优先使用覆盖内容
        scene_override = {
            NoteSceneEnum.MEETING: self.config.prompt_template_meeting,
            NoteSceneEnum.LECTURE: self.config.prompt_template_lecture,
            NoteSceneEnum.INTERVIEW: self.config.prompt_template_interview,
            NoteSceneEnum.GENERAL: self.config.prompt_template_general,
        }.get(self.config.scene, "")

        if scene_override:
            return scene_override

        if template_path.exists():
            return template_path.read_text(encoding="utf-8")

        logger.warning("Prompt 模板文件不存在: %s，使用内置默认模板", template_path)
        return (
            "请将以下转录文本整理为结构清晰的 Markdown 笔记，"
            "提取核心内容，过滤冗余信息。\n\n转录文本：\n\n{{transcript}}"
        )
