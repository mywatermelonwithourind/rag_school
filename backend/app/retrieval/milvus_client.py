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

    q = query.lower()
    if any(term in q for term in ("办公", "办公室", "上班", "工作时间", "地点", "地址")):
        return [
            {"child_chunk_id": "cc_001", "parent_chunk_id": "pc_office_hours", "score": 0.92},
            {"child_chunk_id": "cc_001_b", "parent_chunk_id": "pc_office_hours", "score": 0.86},
            {"child_chunk_id": "cc_004", "parent_chunk_id": "pc_office_location", "score": 0.74},
            {"child_chunk_id": "cc_004_b", "parent_chunk_id": "pc_office_location", "score": 0.68},
            {"child_chunk_id": "cc_003", "parent_chunk_id": "pc_graduation_req", "score": 0.31},
        ][:top_k]

    if any(term in q for term in ("毕业", "学分", "必修", "选修")):
        return [
            {"child_chunk_id": "cc_003", "parent_chunk_id": "pc_graduation_req", "score": 0.89},
            {"child_chunk_id": "cc_003_b", "parent_chunk_id": "pc_graduation_req", "score": 0.83},
            {"child_chunk_id": "cc_005", "parent_chunk_id": "pc_graduation_process", "score": 0.72},
            {"child_chunk_id": "cc_001", "parent_chunk_id": "pc_office_hours", "score": 0.35},
        ][:top_k]

    return [
        {"child_chunk_id": "cc_001", "parent_chunk_id": "pc_office_hours", "score": 0.92},
        {"child_chunk_id": "cc_003", "parent_chunk_id": "pc_graduation_req", "score": 0.78},
    ][:top_k]
