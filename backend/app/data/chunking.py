"""父子切片 — data 组

父块：MySQL 存全文，用于聚合展示与 FAQ 直出
子块：Milvus 存向量，用于召回
"""

from __future__ import annotations

from typing import Any


def chunk_document(
    doc: dict[str, Any],
    parent_size: int = 800,
    child_size: int = 200,
    overlap: int = 50,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    父子切片（含结构化文档语义切分占位）。

    TODO(data):
        - 结构化文档：按标题/段落语义切分
        - 父块 parent_chunk_id 生成规则
        - 子块 child_chunk_id 与 parent 关联

    Args:
        doc: load_document 返回值
        parent_size: 父块目标字符数
        child_size: 子块目标字符数
        overlap: 子块重叠

    Returns:
        (parent_chunks, child_chunks)
    """
    content = doc.get("content", "")
    doc_id = doc.get("doc_id", "unknown")
    kb_id = doc.get("metadata", {}).get("kb_id", "kb_cs_college")

    # 简单按长度切父块（桩）
    parents: list[dict[str, Any]] = []
    children: list[dict[str, Any]] = []

    if not content:
        return parents, children

    step = max(parent_size - overlap, 1)
    for i, start in enumerate(range(0, len(content), step)):
        end = min(start + parent_size, len(content))
        parent_id = f"pc_{doc_id}_{i}"
        parent_text = content[start:end]
        parents.append({
            "parent_chunk_id": parent_id,
            "content": parent_text,
            "doc_id": doc_id,
            "kb_id": kb_id,
            "chunk_index": i,
            "metadata": doc.get("metadata", {}),
        })

        # 子块
        for j, cs in enumerate(range(0, len(parent_text), max(child_size - overlap, 1))):
            ce = min(cs + child_size, len(parent_text))
            children.append({
                "child_chunk_id": f"cc_{doc_id}_{i}_{j}",
                "parent_chunk_id": parent_id,
                "content": parent_text[cs:ce],
                "doc_id": doc_id,
                "kb_id": kb_id,
                "chunk_index": j,
            })

    return parents, children
