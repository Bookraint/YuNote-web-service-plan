import datetime
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional


def _generate_task_id() -> str:
    return uuid.uuid4().hex[:8]


# ──────────────────────────── 格式枚举 ────────────────────────────

class SupportedAudioFormats(Enum):
    AAC  = "aac"
    AIFF = "aiff"
    AMR  = "amr"
    FLAC = "flac"
    M4A  = "m4a"
    MP3  = "mp3"
    OGG  = "ogg"
    OPUS = "opus"
    WAV  = "wav"
    WMA  = "wma"
    WEBM = "webm"


class SupportedVideoFormats(Enum):
    """视频文件也可以直接导入，提取音轨后转录"""
    MP4  = "mp4"
    MOV  = "mov"
    MKV  = "mkv"
    AVI  = "avi"
    WMV  = "wmv"
    FLV  = "flv"
    M4V  = "m4v"
    TS   = "ts"
    WEBM = "webm"


# ──────────────────────────── LLM 枚举 ────────────────────────────

class LLMServiceEnum(Enum):
    OPENAI        = "OpenAI 兼容"
    SILICON_CLOUD = "SiliconCloud"
    DEEPSEEK      = "DeepSeek"
    OLLAMA        = "Ollama"
    LM_STUDIO     = "LM Studio"
    GEMINI        = "Gemini"
    CHATGLM       = "ChatGLM"


# ──────────────────────────── 转录枚举 ────────────────────────────

class TranscribeModelEnum(Enum):
    BIJIAN        = "B 接口"
    JIANYING      = "J 接口"
    ELEVENLABS    = "ElevenLabs Scribe ✨"
    WHISPER_API   = "Whisper [API] ✨"
    FASTER_WHISPER = "FasterWhisper ✨"
    WHISPER_CPP   = "WhisperCpp"


class TranscribeLanguageEnum(Enum):
    AUTO       = "自动检测"
    ENGLISH    = "英语"
    CHINESE    = "中文"
    JAPANESE   = "日本語"
    KOREAN     = "韩语"
    YUE        = "粤语"
    FRENCH     = "法语"
    GERMAN     = "德语"
    SPANISH    = "西班牙语"
    RUSSIAN    = "俄语"
    PORTUGUESE = "葡萄牙语"
    TURKISH    = "土耳其语"
    ARABIC     = "阿拉伯语"
    ITALIAN    = "意大利语"
    DUTCH      = "荷兰语"
    POLISH     = "波兰语"
    VIETNAMESE = "越南语"
    THAI       = "泰语"
    HINDI      = "印地语"
    INDONESIAN = "印度尼西亚语"
    UKRAINIAN  = "乌克兰语"
    SWEDISH    = "瑞典语"


class WhisperModelEnum(Enum):
    TINY     = "tiny"
    BASE     = "base"
    SMALL    = "small"
    MEDIUM   = "medium"
    LARGE_V1 = "large-v1"
    LARGE_V2 = "large-v2"


class FasterWhisperModelEnum(Enum):
    TINY            = "tiny"
    BASE            = "base"
    SMALL           = "small"
    MEDIUM          = "medium"
    LARGE_V1        = "large-v1"
    LARGE_V2        = "large-v2"
    LARGE_V3        = "large-v3"
    LARGE_V3_TURBO  = "large-v3-turbo"


class VadMethodEnum(Enum):
    SILERO_V3        = "silero_v3"
    SILERO_V4        = "silero_v4"
    SILERO_V5        = "silero_v5"
    SILERO_V4_FW     = "silero_v4_fw"
    PYANNOTE_V3      = "pyannote_v3"
    PYANNOTE_ONNX_V3 = "pyannote_onnx_v3"
    WEBRTC           = "webrtc"
    AUDITOK          = "auditok"


class TranscribeOutputFormatEnum(Enum):
    SRT = "SRT"
    TXT = "TXT"
    ALL = "All"


# ──────────────────────────── YuNote 枚举 ────────────────────────────

class NoteSceneEnum(Enum):
    MEETING   = "会议"
    LECTURE   = "课程"
    INTERVIEW = "访谈"
    GENERAL   = "通用"


class TaskStatusEnum(Enum):
    PENDING  = "等待中"
    RUNNING  = "处理中"
    DONE     = "已完成"
    FAILED   = "失败"


class SubtitleLayoutEnum(Enum):
    """保留供 asr_data.py 使用（转录原文/译文布局）"""
    TRANSLATE_ON_TOP = "译文在上"
    ORIGINAL_ON_TOP  = "原文在上"
    ONLY_ORIGINAL    = "仅原文"
    ONLY_TRANSLATE   = "仅译文"


# ──────────────────────────── 语言映射 ────────────────────────────

LANGUAGES = {
    "自动检测": "",
    "英语": "en",
    "中文": "zh",
    "日本語": "ja",
    "德语": "de",
    "粤语": "yue",
    "西班牙语": "es",
    "俄语": "ru",
    "韩语": "ko",
    "法语": "fr",
    "葡萄牙语": "pt",
    "土耳其语": "tr",
    "阿拉伯语": "ar",
    "意大利语": "it",
    "荷兰语": "nl",
    "波兰语": "pl",
    "越南语": "vi",
    "泰语": "th",
    "印地语": "hi",
    "印度尼西亚语": "id",
    "乌克兰语": "uk",
    "瑞典语": "sv",
    # Whisper 英文语言名 → 代码（兼容旧数据）
    "English": "en",
    "Chinese": "zh",
    "German": "de",
    "Spanish": "es",
    "Russian": "ru",
    "Korean": "ko",
    "French": "fr",
    "Japanese": "ja",
    "Portuguese": "pt",
    "Turkish": "tr",
    "Arabic": "ar",
    "Italian": "it",
    "Dutch": "nl",
    "Polish": "pl",
    "Vietnamese": "vi",
    "Thai": "th",
    "Hindi": "hi",
    "Indonesian": "id",
    "Ukrainian": "uk",
    "Swedish": "sv",
    "Cantonese": "yue",
}


# ──────────────────────────── ASR 语言能力 ────────────────────────────

@dataclass
class ASRLanguageCapability:
    supported_languages: list[TranscribeLanguageEnum]
    supports_auto: bool


def _get_all_languages_except_auto() -> list[TranscribeLanguageEnum]:
    return [lang for lang in TranscribeLanguageEnum if lang != TranscribeLanguageEnum.AUTO]


ASR_LANGUAGE_CAPABILITIES: dict[TranscribeModelEnum, ASRLanguageCapability] = {
    TranscribeModelEnum.BIJIAN: ASRLanguageCapability(
        supported_languages=[TranscribeLanguageEnum.CHINESE, TranscribeLanguageEnum.ENGLISH],
        supports_auto=True,
    ),
    TranscribeModelEnum.JIANYING: ASRLanguageCapability(
        supported_languages=[TranscribeLanguageEnum.CHINESE, TranscribeLanguageEnum.ENGLISH],
        supports_auto=True,
    ),
    TranscribeModelEnum.FASTER_WHISPER: ASRLanguageCapability(
        supported_languages=_get_all_languages_except_auto(),
        supports_auto=False,
    ),
    TranscribeModelEnum.WHISPER_CPP: ASRLanguageCapability(
        supported_languages=_get_all_languages_except_auto(),
        supports_auto=True,
    ),
    TranscribeModelEnum.WHISPER_API: ASRLanguageCapability(
        supported_languages=_get_all_languages_except_auto(),
        supports_auto=True,
    ),
    TranscribeModelEnum.ELEVENLABS: ASRLanguageCapability(
        supported_languages=_get_all_languages_except_auto(),
        supports_auto=True,
    ),
}


def get_asr_language_capability(model: TranscribeModelEnum) -> ASRLanguageCapability:
    return ASR_LANGUAGE_CAPABILITIES.get(
        model,
        ASRLanguageCapability(supported_languages=_get_all_languages_except_auto(), supports_auto=True),
    )


# ──────────────────────────── 转录配置 & 任务 ────────────────────────────

@dataclass
class TranscribeConfig:
    transcribe_model: Optional[TranscribeModelEnum] = None
    transcribe_language: str = ""
    need_word_time_stamp: bool = False
    output_format: Optional[TranscribeOutputFormatEnum] = TranscribeOutputFormatEnum.TXT
    # Whisper Cpp
    whisper_model: Optional[WhisperModelEnum] = None
    # Whisper API
    whisper_api_key: Optional[str] = None
    whisper_api_base: Optional[str] = None
    whisper_api_model: Optional[str] = None
    whisper_api_prompt: Optional[str] = None
    # FasterWhisper
    faster_whisper_program: Optional[str] = None
    faster_whisper_model: Optional[FasterWhisperModelEnum] = None
    faster_whisper_model_dir: Optional[str] = None
    faster_whisper_device: str = "cuda"
    faster_whisper_vad_filter: bool = True
    faster_whisper_vad_threshold: float = 0.4
    faster_whisper_vad_method: Optional[VadMethodEnum] = VadMethodEnum.SILERO_V4
    faster_whisper_ff_mdx_kim2: bool = False
    faster_whisper_one_word: bool = True
    faster_whisper_prompt: Optional[str] = None
    # ElevenLabs Scribe（allow_unauthenticated，无 API Key）
    elevenlabs_model_id: str = "scribe_v1"
    elevenlabs_diarize: bool = True
    elevenlabs_tag_audio_events: bool = False
    # 分块 / 并发 / 限流（长音频）
    transcribe_enable_async: bool = True
    transcribe_max_concurrent_chunks: int = 3
    transcribe_chunk_max_retries: int = 3
    transcribe_api_rate_limit_per_minute: int = 30
    transcribe_split_threshold_minutes: int = 90
    transcribe_chunk_length_minutes: int = 20

    def _mask_key(self, key: Optional[str]) -> str:
        if not key or len(key) <= 12:
            return "****"
        return f"{key[:4]}...{key[-4:]}"

    def print_config(self) -> str:
        lines = ["=========== Transcription Config ==========="]
        lines.append(f"Model: {self.transcribe_model.value if self.transcribe_model else 'None'}")
        lines.append(f"Language: {self.transcribe_language or 'Auto'}")
        if self.transcribe_model == TranscribeModelEnum.WHISPER_API:
            lines.append(f"API Base: {self.whisper_api_base}")
            lines.append(f"API Key: {self._mask_key(self.whisper_api_key)}")
            lines.append(f"API Model: {self.whisper_api_model}")
        elif self.transcribe_model == TranscribeModelEnum.ELEVENLABS:
            lines.append(f"ElevenLabs Model: {self.elevenlabs_model_id}")
            lines.append(f"Diarize: {self.elevenlabs_diarize}")
        elif self.transcribe_model == TranscribeModelEnum.FASTER_WHISPER:
            lines.append(f"FW Model: {self.faster_whisper_model.value if self.faster_whisper_model else 'None'}")
            lines.append(f"Device: {self.faster_whisper_device}")
            lines.append(f"VAD: {self.faster_whisper_vad_filter}")
        lines.append(
            f"Chunk: async={self.transcribe_enable_async}, "
            f"concurrent={self.transcribe_max_concurrent_chunks}, "
            f"retries={self.transcribe_chunk_max_retries}, "
            f"rate_limit={self.transcribe_api_rate_limit_per_minute}/min, "
            f"split_threshold={self.transcribe_split_threshold_minutes}min, "
            f"chunk_len={self.transcribe_chunk_length_minutes}min"
        )
        lines.append("=" * 44)
        return "\n".join(lines)


@dataclass
class TranscribeTask:
    task_id: str = field(default_factory=_generate_task_id)
    queued_at: Optional[datetime.datetime] = None
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None

    file_path: Optional[str] = None       # 音频文件路径（预处理后的 WAV）
    output_path: Optional[str] = None     # 转录文本输出路径
    need_next_task: bool = True           # 完成后自动触发总结
    note_id: Optional[str] = None        # 关联笔记 ID

    transcribe_config: Optional[TranscribeConfig] = None


# ──────────────────────────── 总结配置 & 任务 ────────────────────────────

@dataclass
class SummaryConfig:
    scene: NoteSceneEnum = NoteSceneEnum.GENERAL
    llm_service: LLMServiceEnum = LLMServiceEnum.OPENAI
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    custom_prompt: str = ""         # 用户追加指令
    # 用户可编辑的“场景模板”覆盖内容；为空时回退到 resource/prompts/summary_*.md
    prompt_template_meeting: str = ""
    prompt_template_lecture: str = ""
    prompt_template_interview: str = ""
    prompt_template_general: str = ""
    chunk_size: int = 4000          # 单块最大字符数（Map-Reduce 分块）
    map_concurrency: int = 3       # Map 阶段同时请求数（1=顺序）
    map_rpm: int = 60              # Map 阶段 API 每分钟请求上限；0=不限
    prompts_path: str = ""          # resource/prompts/ 路径
    llm_timeout_sec: float = 600.0  # 单次 chat.completions 请求超时（秒），避免永久挂起

    def _mask_key(self, key: str) -> str:
        if not key or len(key) <= 12:
            return "****"
        return f"{key[:4]}...{key[-4:]}"

    def print_config(self) -> str:
        lines = ["=========== Summary Config ==========="]
        lines.append(f"Scene: {self.scene.value}")
        lines.append(f"LLM: {self.llm_service.value} / {self.llm_model}")
        lines.append(f"API Base: {self.llm_base_url}")
        lines.append(f"API Key: {self._mask_key(self.llm_api_key)}")
        lines.append(f"Chunk Size: {self.chunk_size}")
        lines.append(f"Map Concurrency: {self.map_concurrency}, RPM: {self.map_rpm}")
        lines.append("=" * 38)
        return "\n".join(lines)


@dataclass
class SummaryTask:
    task_id: str = field(default_factory=_generate_task_id)
    queued_at: Optional[datetime.datetime] = None
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None

    transcript_path: Optional[str] = None      # 转录文本输入
    output_summary_path: Optional[str] = None  # Markdown 总结输出
    note_id: Optional[str] = None

    summary_config: Optional[SummaryConfig] = None


# ──────────────────────────── 笔记 ────────────────────────────

@dataclass
class Note:
    """
    一条笔记的完整元数据。
    note_id 与目录名一致，形如「音频主文件名_YYYYMMDD_HHMMSS」。
    meta.json 保存可检索字段（标题、场景、状态等），与 transcript/summary 分离，便于列表与增量更新。
    """
    note_id: str = field(default_factory=_generate_task_id)
    title: str = ""
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.now)

    scene: NoteSceneEnum = NoteSceneEnum.GENERAL
    tags: list[str] = field(default_factory=list)

    source_audio_name: str = ""         # 原始文件名（仅记录，不保存音频）
    duration_seconds: float = 0.0       # 音频时长（秒）

    transcript_file: str = "transcript.txt"
    summary_file: str = "summary.md"

    transcribe_model: str = ""
    llm_model: str = ""

    status: TaskStatusEnum = TaskStatusEnum.PENDING
