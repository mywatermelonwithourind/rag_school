"""公共工具函数。"""

from __future__ import annotations

import re
import uuid


def new_session_id() -> str:
    return str(uuid.uuid4())


def normalize_text(text: str) -> str:
    """基础文本清洗：去首尾空白、合并连续空白。"""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text


def truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
