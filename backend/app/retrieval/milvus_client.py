"""Milvus 向量检索客户端 — retrieval 组"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings

# TODO(retrieval): from pymilvus import connections, Collection


def search_child_chunks(query: str, top_k: int = 20) -> list[dict[str, Any]]:
    """
    Milvus 子块向量检索。

    TODO(retrieval):
        - connections.connect(host, port)
        - collection.search(data=[embedding], anns_field="embedding", ...)

    当前返回 mock 子块命中。
    """
    settings = get_settings()
    _ = settings  # 后续连接 Milvus

    return [
        {"child_chunk_id": "cc_001", "parent_chunk_id": "pc_office_hours", "score": 0.92},
        {"child_chunk_id": "cc_003", "parent_chunk_id": "pc_graduation_req", "score": 0.78},
    ][:top_k]
