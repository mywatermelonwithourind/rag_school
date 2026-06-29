"""Milvus 向量检索客户端 — retrieval 组"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.retrieval.embedding import embed_texts

_MILVUS_ALIAS = "rag_ingest"
logger = logging.getLogger(__name__)


def _connect_milvus() -> None:
    from pymilvus import connections

    settings = get_settings()
    connections.connect(
        alias=_MILVUS_ALIAS,
        host=settings.milvus_host,
        port=str(settings.milvus_port),
        timeout=float(settings.milvus_timeout_seconds),
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

    查询侧允许 embedding fallback；Milvus 不可用时返回空召回并记录日志，
    由 pipeline 判定 retrieval_sufficient=False。
    """
    settings = get_settings()
    if not query.strip() or top_k <= 0:
        return []

    try:
        query_vector = embed_texts([query])[0]
        collection = _get_or_create_collection()
        collection.load()
        results = collection.search(
            data=[query_vector],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 10}},
            limit=top_k,
            output_fields=[
                "child_chunk_id",
                "parent_chunk_id",
                "content",
                "doc_id",
                "kb_id",
                "chunk_index",
            ],
            timeout=float(settings.milvus_timeout_seconds),
        )
    except Exception:
        logger.exception("Milvus child chunk search failed; returning empty recall")
        return []

    hits = results[0] if results else []
    child_chunks: list[dict[str, Any]] = []
    for hit in hits:
        entity = getattr(hit, "entity", None)
        child_chunks.append(
            {
                "child_chunk_id": _read_hit_value(hit, entity, "child_chunk_id"),
                "parent_chunk_id": _read_hit_value(hit, entity, "parent_chunk_id"),
                "content": _read_hit_value(hit, entity, "content"),
                "doc_id": _read_hit_value(hit, entity, "doc_id"),
                "kb_id": _read_hit_value(hit, entity, "kb_id"),
                "chunk_index": _read_hit_value(hit, entity, "chunk_index"),
                "score": _normalize_cosine_score(float(getattr(hit, "score", 0.0) or 0.0)),
                "raw_score": float(getattr(hit, "score", 0.0) or 0.0),
            }
        )
    return child_chunks


def _read_hit_value(hit: Any, entity: Any, field: str) -> Any:
    if entity is not None:
        try:
            return entity.get(field)
        except Exception:
            pass
    try:
        return hit.get(field)
    except Exception:
        return None


def _normalize_cosine_score(score: float) -> float:
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return score
