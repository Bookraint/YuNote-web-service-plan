import platform
import subprocess
import json
from pathlib import Path
from typing import Optional

from core.utils.logger import setup_logger


def _subprocess_kwargs() -> dict:
    """Windows 桌面应用防止弹出黑色 cmd 窗口；服务端返回空 dict 即可。"""
    if platform.system() == "Windows" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}

logger = setup_logger("audio_utils")

SUPPORTED_AUDIO_EXTS = {
    ".aac", ".aiff", ".amr", ".flac", ".m4a",
    ".mp3", ".ogg", ".opus", ".wav", ".wma", ".webm",
}
SUPPORTED_VIDEO_EXTS = {
    ".mp4", ".mov", ".mkv", ".avi", ".wmv",
    ".flv", ".m4v", ".ts", ".webm",
}
SUPPORTED_EXTS = SUPPORTED_AUDIO_EXTS | SUPPORTED_VIDEO_EXTS


def is_supported(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in SUPPORTED_EXTS


def get_duration(file_path: str) -> float:
    """
    用 ffprobe 获取音视频文件时长（秒）。
    若 ffprobe 不可用则返回 0.0。
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            **_subprocess_kwargs(),
        )
        info = json.loads(result.stdout)
        return float(info.get("format", {}).get("duration", 0))
    except Exception as e:
        logger.warning("获取时长失败 %s: %s", file_path, e)
        return 0.0


def format_duration(seconds: float) -> str:
    """将秒数格式化为 HH:MM:SS 或 MM:SS。"""
    s = int(seconds)
    h, remainder = divmod(s, 3600)
    m, sec = divmod(remainder, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def convert_to_wav(
    input_path: str,
    output_path: str,
    sample_rate: int = 16000,
) -> bool:
    """
    将音视频文件转换为 16kHz 单声道 WAV，供 Whisper 转录使用。

    Args:
        input_path: 输入文件路径
        output_path: 输出 WAV 路径
        sample_rate: 采样率，默认 16000Hz

    Returns:
        转换成功返回 True，否则 False。
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vn",                      # 不含视频流
        "-acodec", "pcm_s16le",     # 16-bit PCM
        "-ar", str(sample_rate),    # 采样率
        "-ac", "1",                 # 单声道
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            **_subprocess_kwargs(),
        )
        if result.returncode != 0:
            logger.error("ffmpeg 转换失败:\n%s", result.stderr)
            return False
        logger.info("音频转换完成: %s → %s", input_path, output_path)
        return True
    except FileNotFoundError:
        logger.error("未找到 ffmpeg，请确认已安装并加入 PATH")
        return False
    except subprocess.TimeoutExpired:
        logger.error("音频转换超时: %s", input_path)
        return False
    except Exception as e:
        logger.error("音频转换异常: %s", e)
        return False


def needs_conversion(file_path: str) -> bool:
    """判断是否需要转换（视频文件或非 WAV 音频均需转换）。"""
    suffix = Path(file_path).suffix.lower()
    return suffix != ".wav" or suffix in SUPPORTED_VIDEO_EXTS


def prepare_audio(
    input_path: str,
    note_dir: str,
) -> Optional[str]:
    """
    预处理入口：若需要则转换格式，否则直接返回原路径。

    转换后的 WAV 写在笔记目录内 ``{note_dir}/audio.wav``，与 transcript 同目录，
    处理完成后可按设置删除，不再使用单独的 work-dir。

    Args:
        input_path: 用户导入的原始文件
        note_dir: 笔记目录路径（设置中的笔记存储目录/{note_id}/）

    Returns:
        可直接送入 ASR 的 WAV 文件路径，失败返回 None。
    """
    if not is_supported(input_path):
        logger.error("不支持的文件格式: %s", input_path)
        return None

    if not needs_conversion(input_path):
        logger.info("音频格式无需转换: %s", input_path)
        return input_path

    Path(note_dir).mkdir(parents=True, exist_ok=True)
    wav_path = str(Path(note_dir) / "audio.wav")
    success = convert_to_wav(input_path, wav_path)
    return wav_path if success else None
