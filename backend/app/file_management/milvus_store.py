"""Milvus operations used only by the file-management API."""

from __future__ import annotations

import json
import threading
from collections import Counter
from typing import Any

from app.core.config import get_settings

_ALIAS = "rag_file_management"
_LOCK = threading.RLock()
_SCALAR_FIELDS = [
    "child_chunk_id",
    "parent_chunk_id",
    "content",
    "doc_id",
    "kb_id",
    "chunk_index",
]


def _get_collection():
    from pymilvus import Collection, connections, utility

    settings = get_settings()
    if not connections.has_connection(_ALIAS):
        connections.connect(
            alias=_ALIAS,
            host=settings.milvus_host,
            port=str(settings.milvus_port),
            timeout=float(settings.milvus_timeout_seconds),
        )
    if not utility.has_collection(settings.milvus_collection, using=_ALIAS):
        raise RuntimeError(f"Milvus collection 不存在: {settings.milvus_collection}")

    collection = Collection(settings.milvus_collection, using=_ALIAS)
    collection.load()
    return collection


def _equal_expr(field: str, value: str) -> str:
    return f"{field} == {json.dumps(value, ensure_ascii=False)}"


def _iter_query(*, expr: str, output_fields: list[str]) -> list[dict[str, Any]]:
    collection = _get_collection()
    iterator = collection.query_iterator(
        expr=expr,
        output_fields=output_fields,
        batch_size=500,
        consistency_level="Strong",
    )
    rows: list[dict[str, Any]] = []
    try:
        while True:
            batch = iterator.next()
            if not batch:
                break
            rows.extend(dict(item) for item in batch)
    finally:
        iterator.close()
    return rows


def count_vectors(file_id: str) -> int:
    with _LOCK:
        rows = _get_collection().query(
            expr=_equal_expr("doc_id", file_id),
            output_fields=["count(*)"],
            consistency_level="Strong",
        )
    return int(rows[0].get("count(*)", 0)) if rows else 0


def count_vectors_by_file(kb_id: str) -> dict[str, int]:
    with _LOCK:
        rows = _iter_query(
            expr=_equal_expr("kb_id", kb_id),
            output_fields=["doc_id"],
        )
    return dict(Counter(str(row.get("doc_id") or "") for row in rows if row.get("doc_id")))


def list_child_chunks(file_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        rows = _iter_query(
            expr=_equal_expr("doc_id", file_id),
            output_fields=_SCALAR_FIELDS,
        )
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("parent_chunk_id") or ""),
            int(row.get("chunk_index") or 0),
            str(row.get("child_chunk_id") or ""),
        ),
    )


def snapshot_vectors(file_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        return _iter_query(
            expr=_equal_expr("doc_id", file_id),
            output_fields=[*_SCALAR_FIELDS, "embedding"],
        )


def delete_vectors(file_id: str) -> int:
    with _LOCK:
        collection = _get_collection()
        result = collection.delete(expr=_equal_expr("doc_id", file_id))
        collection.flush()
    return int(getattr(result, "delete_count", 0) or 0)


def restore_vectors(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    with _LOCK:
        collection = _get_collection()
        data = [
            [str(row["child_chunk_id"]) for row in rows],
            [str(row["parent_chunk_id"]) for row in rows],
            [str(row.get("content") or "") for row in rows],
            [str(row.get("doc_id") or "") for row in rows],
            [str(row.get("kb_id") or "") for row in rows],
            [int(row.get("chunk_index") or 0) for row in rows],
            [list(row["embedding"]) for row in rows],
        ]
        collection.upsert(data)
        collection.flush()
    return len(rows)
