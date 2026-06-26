"""父子切片 — data 组

父块：MySQL 存全文，用于聚合展示与 FAQ 直出
子块：Milvus 存向量，用于召回
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

PARENT_TOKEN_SIZE = 2000
CHILD_MIN_TOKENS = 150
CHILD_TARGET_TOKENS = 200
CHILD_MAX_TOKENS = 250


def _safe_id_part(value: str, max_len: int = 36) -> str:
    compact = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", value).strip("_")
    compact = compact or "doc"
    suffix = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return f"{compact[:max_len]}_{suffix}"


def estimate_token_count(text: str) -> int:
    """
    Lightweight token estimate for Chinese/English mixed documents.

    This keeps the chunking contract local and dependency-free. Swap this function
    for a tokenizer-specific implementation when the embedding model tokenizer is
    available.
    """
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    words = len(re.findall(r"[A-Za-z0-9]+(?:[-_./][A-Za-z0-9]+)*", text))
    punctuation = len(re.findall(r"[^\w\s\u4e00-\u9fff]", text))
    return max(1, cjk + words + punctuation // 2)


def _semantic_units(text: str) -> list[str]:
    """Split text into paragraph/sentence semantic units."""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    units: list[str] = []
    sentence_pattern = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")

    for paragraph in paragraphs:
        if estimate_token_count(paragraph) <= CHILD_MAX_TOKENS:
            units.append(paragraph)
            continue
        sentences = [m.group(0).strip() for m in sentence_pattern.finditer(paragraph)]
        units.extend(sentence for sentence in sentences if sentence)

    return units or ([text.strip()] if text.strip() else [])


def _split_large_unit(unit: str, max_tokens: int) -> list[str]:
    """Hard-split a unit that exceeds the target token budget."""
    if estimate_token_count(unit) <= max_tokens:
        return [unit]

    parts: list[str] = []
    current: list[str] = []
    for char in unit:
        current.append(char)
        if estimate_token_count("".join(current)) >= max_tokens:
            parts.append("".join(current).strip())
            current = []
    if current:
        parts.append("".join(current).strip())
    return [part for part in parts if part]


def _pack_units(units: list[str], *, min_tokens: int, target_tokens: int, max_tokens: int) -> list[str]:
    """Pack semantic units into chunks around target_tokens without exceeding max_tokens."""
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for raw_unit in units:
        for unit in _split_large_unit(raw_unit, max_tokens):
            unit_tokens = estimate_token_count(unit)
            separator_tokens = 1 if current else 0
            would_exceed = current and current_tokens + separator_tokens + unit_tokens > max_tokens
            target_reached = current and current_tokens >= min_tokens and (
                current_tokens + separator_tokens + unit_tokens > target_tokens
            )

            if would_exceed or target_reached:
                chunks.append("\n".join(current).strip())
                current = []
                current_tokens = 0

            current.append(unit)
            current_tokens += unit_tokens + (1 if current_tokens else 0)

    if current:
        tail = "\n".join(current).strip()
        if chunks and estimate_token_count(tail) < min_tokens:
            merged = f"{chunks[-1]}\n{tail}".strip()
            if estimate_token_count(merged) <= max_tokens:
                chunks[-1] = merged
            else:
                chunks.append(tail)
        else:
            chunks.append(tail)

    return [chunk for chunk in chunks if chunk]


def chunk_document(
    doc: dict[str, Any],
    parent_size: int = PARENT_TOKEN_SIZE,
    child_min_tokens: int = CHILD_MIN_TOKENS,
    child_target_tokens: int = CHILD_TARGET_TOKENS,
    child_max_tokens: int = CHILD_MAX_TOKENS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    父子切片（含结构化文档语义切分占位）。

    TODO(data):
    Args:
        doc: load_document 返回值
        parent_size: 父块目标 token 数
        child_min_tokens: 子块最小 token 数
        child_target_tokens: 子块目标 token 数
        child_max_tokens: 子块最大 token 数

    Returns:
        (parent_chunks, child_chunks)
    """
    content = doc.get("content", "")
    raw_doc_id = str(doc.get("doc_id", "unknown"))
    doc_id = _safe_id_part(raw_doc_id, max_len=40)
    kb_id = doc.get("metadata", {}).get("kb_id", "kb_cs_college")

    parents: list[dict[str, Any]] = []
    children: list[dict[str, Any]] = []

    if not content:
        return parents, children

    semantic_units = _semantic_units(content)
    parent_texts = _pack_units(
        semantic_units,
        min_tokens=max(parent_size - 200, 1),
        target_tokens=parent_size,
        max_tokens=parent_size,
    )

    for i, parent_text in enumerate(parent_texts):
        parent_id = f"pc_{doc_id}_{i}"
        parents.append({
            "parent_chunk_id": parent_id,
            "content": parent_text,
            "doc_id": doc_id,
            "kb_id": kb_id,
            "chunk_index": i,
            "title": doc.get("title") or raw_doc_id,
            "metadata": doc.get("metadata", {}),
        })

        child_texts = _pack_units(
            _semantic_units(parent_text),
            min_tokens=child_min_tokens,
            target_tokens=child_target_tokens,
            max_tokens=child_max_tokens,
        )
        for j, child_text in enumerate(child_texts):
            children.append({
                "child_chunk_id": f"cc_{doc_id}_{i}_{j}",
                "parent_chunk_id": parent_id,
                "content": child_text,
                "doc_id": doc_id,
                "kb_id": kb_id,
                "chunk_index": j,
            })

    return parents, children
