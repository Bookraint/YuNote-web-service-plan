"""
按句子边界将长文本分块，确保每块不超过 chunk_size 字符。
块间保留 overlap_size 字符的重叠以保持上下文连贯性。
"""
import re


def split_into_chunks(text: str, chunk_size: int = 4000, overlap: int = 200) -> list[str]:
    """
    将文本按句子边界分块。

    Args:
        text: 待分块的原始文本
        chunk_size: 每块最大字符数
        overlap: 相邻块之间的重叠字符数

    Returns:
        分块列表；若文本长度不超过 chunk_size，直接返回单元素列表。
    """
    if len(text) <= chunk_size:
        return [text]

    sentences = _split_sentences(text)
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for sentence in sentences:
        sentence_len = len(sentence)

        if current_len + sentence_len > chunk_size and current_chunk:
            chunk_text = "".join(current_chunk)
            chunks.append(chunk_text)

            # 保留末尾若干字符作为下一块的重叠前缀
            overlap_text = chunk_text[-overlap:] if overlap > 0 else ""
            current_chunk = [overlap_text] if overlap_text else []
            current_len = len(overlap_text)

        current_chunk.append(sentence)
        current_len += sentence_len

    if current_chunk:
        chunks.append("".join(current_chunk))

    return chunks


def _split_sentences(text: str) -> list[str]:
    """按中英文句末标点切分句子，保留标点。"""
    pattern = r"(?<=[。！？.!?])\s*"
    parts = re.split(pattern, text)
    sentences = [p for p in parts if p.strip()]
    return sentences
