"""Milvus 向量检索客户端 — retrieval 组"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.workflow.state import SourceChunk

_MILVUS_ALIAS = "rag_ingest"


def _connect_milvus() -> None:
    from pymilvus import connections

    settings = get_settings()
    connections.connect(
        alias=_MILVUS_ALIAS,
        host=settings.milvus_host,
        port=str(settings.milvus_port),
    )


def _get_or_create_collection():
    from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, utility

    settings = get_settings()
    _connect_milvus()
    if utility.has_collection(settings.milvus_collection, using=_MILVUS_ALIAS):
        return Collection(settings.milvus_collection, using=_MILVUS_ALIAS)

    fields = [
        FieldSchema("child_chunk_id", DataType.VARCHAR, is_primary=True, max_length=128),
        FieldSchema("parent_chunk_id", DataType.VARCHAR, max_length=128),
        FieldSchema("content", DataType.VARCHAR, max_length=8192),
        FieldSchema("doc_id", DataType.VARCHAR, max_length=128),
        FieldSchema("kb_id", DataType.VARCHAR, max_length=128),
        FieldSchema("chunk_index", DataType.INT64),
        FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=settings.milvus_dim),
    ]
    schema = CollectionSchema(fields, description="RAG child chunks")
    collection = Collection(settings.milvus_collection, schema=schema, using=_MILVUS_ALIAS)
    collection.create_index(
        field_name="embedding",
        index_params={
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": 128},
        },
    )
    return collection


def upsert_child_chunks(
    child_chunks: list[dict[str, Any]],
    embeddings: list[list[float]],
) -> int:
    """Upsert child chunks into Milvus. Raises if Milvus is unavailable."""
    if not child_chunks:
        return 0
    if len(child_chunks) != len(embeddings):
        raise ValueError("child_chunks and embeddings length mismatch")

    collection = _get_or_create_collection()
    data = [
        [str(chunk["child_chunk_id"])[:128] for chunk in child_chunks],
        [str(chunk["parent_chunk_id"])[:128] for chunk in child_chunks],
        [str(chunk.get("content", ""))[:8192] for chunk in child_chunks],
        [str(chunk.get("doc_id", ""))[:128] for chunk in child_chunks],
        [str(chunk.get("kb_id", ""))[:128] for chunk in child_chunks],
        [int(chunk.get("chunk_index", 0) or 0) for chunk in child_chunks],
        embeddings,
    ]
    collection.upsert(data)
    collection.flush()
    return len(child_chunks)


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
