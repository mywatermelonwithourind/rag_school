"""入库脚本 — data 组

将父块写入 MySQL，子块 embedding 后写入 Milvus。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.dialects.mysql import insert

from app.core.database import get_db_session
from app.core.models import KbDocumentRecord, ParentChunkRecord
from app.data.chunking import chunk_document
from app.data.loader import load_document_from_bytes, load_documents_from_dir
from app.retrieval.embedding import embed_texts
from app.retrieval.milvus_client import upsert_child_chunks


def _repo_backend_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def default_raw_data_dir() -> Path:
    return _repo_backend_dir() / "data" / "raw"


def resolve_ingest_dir(dir_path: str | None = None) -> Path:
    """Resolve an ingest path and keep it inside backend/data."""
    data_root = (_repo_backend_dir() / "data").resolve()
    path = Path(dir_path or default_raw_data_dir())
    if not path.is_absolute():
        path = data_root / path
    resolved = path.resolve()
    if resolved != data_root and data_root not in resolved.parents:
        raise ValueError(f"入库目录必须位于 {data_root} 内")
    return resolved


def _upsert_parent_chunks(parent_chunks: list[dict[str, Any]]) -> int:
    if not parent_chunks:
        return 0

    rows = [
        {
            "parent_chunk_id": chunk["parent_chunk_id"],
            "content": chunk["content"],
            "doc_id": chunk["doc_id"],
            "kb_id": chunk["kb_id"],
            "chunk_index": chunk["chunk_index"],
            "title": chunk.get("title"),
            "metadata": chunk.get("metadata") or {},
        }
        for chunk in parent_chunks
    ]

    table = ParentChunkRecord.__table__
    with get_db_session() as db:
        stmt = insert(table).values(rows)
        update_columns = {
            "content": stmt.inserted.content,
            "doc_id": stmt.inserted.doc_id,
            "kb_id": stmt.inserted.kb_id,
            "chunk_index": stmt.inserted.chunk_index,
            "title": stmt.inserted.title,
            "metadata": stmt.inserted["metadata"],
        }
        db.execute(stmt.on_duplicate_key_update(**update_columns))
    return len(rows)


def _upsert_document_record(
    *,
    doc: dict[str, Any],
    kb_id: str,
    doc_id: str,
    parent_count: int,
    child_count: int,
    vector_count: int,
    warnings: list[str],
    skipped: bool,
) -> None:
    metadata = dict(doc.get("metadata") or {})
    table = KbDocumentRecord.__table__
    status = "failed" if skipped else ("partial" if warnings else "ready")
    row = {
        "doc_id": doc_id,
        "kb_id": kb_id,
        "title": str(doc.get("title") or doc_id),
        "source_name": str(metadata.get("source_name") or metadata.get("source_path") or doc.get("title") or doc_id),
        "file_ext": str(metadata.get("format") or ""),
        "source_type": str(metadata.get("source_type") or "directory"),
        "source_path": metadata.get("source_path"),
        "content_chars": len(str(doc.get("content") or "")),
        "parent_count": parent_count,
        "child_count": child_count,
        "vector_count": vector_count,
        "status": status,
        "warnings": warnings,
        "metadata": metadata,
    }
    with get_db_session() as db:
        stmt = insert(table).values(row)
        update_columns = {
            "kb_id": stmt.inserted.kb_id,
            "title": stmt.inserted.title,
            "source_name": stmt.inserted.source_name,
            "file_ext": stmt.inserted.file_ext,
            "source_type": stmt.inserted.source_type,
            "source_path": stmt.inserted.source_path,
            "content_chars": stmt.inserted.content_chars,
            "parent_count": stmt.inserted.parent_count,
            "child_count": stmt.inserted.child_count,
            "vector_count": stmt.inserted.vector_count,
            "status": stmt.inserted.status,
            "warnings": stmt.inserted.warnings,
            "metadata": stmt.inserted["metadata"],
        }
        db.execute(stmt.on_duplicate_key_update(**update_columns))


def _ingest_documents(
    docs: list[dict[str, Any]],
    *,
    kb_id: str,
    source_label: str,
    write_vectors: bool,
    fail_on_vector_error: bool,
) -> dict[str, Any]:
    total_parents = 0
    total_children = 0
    total_parent_upserts = 0
    total_vector_upserts = 0
    skipped_docs: list[str] = []
    warnings: list[str] = []

    for doc in docs:
        doc_warnings = [str(item) for item in doc.get("warnings", [])]
        warnings.extend(f"{doc.get('doc_id')}: {item}" for item in doc_warnings)
        if not doc.get("content"):
            skipped_docs.append(str(doc.get("doc_id", "unknown")))
            _upsert_document_record(
                doc=doc,
                kb_id=kb_id,
                doc_id=str(doc.get("doc_id", "unknown")),
                parent_count=0,
                child_count=0,
                vector_count=0,
                warnings=doc_warnings,
                skipped=True,
            )
            continue

        doc.setdefault("metadata", {})["kb_id"] = kb_id
        parents, children = chunk_document(doc)
        doc_id = parents[0]["doc_id"] if parents else str(doc.get("doc_id", "unknown"))
        doc_vector_upserts = 0
        total_parents += len(parents)
        total_children += len(children)
        total_parent_upserts += _upsert_parent_chunks(parents)

        if write_vectors and children:
            texts = [c["content"] for c in children]
            try:
                embeddings = embed_texts(texts, allow_fallback=False)
                doc_vector_upserts = upsert_child_chunks(children, embeddings)
                total_vector_upserts += doc_vector_upserts
            except Exception as exc:
                message = f"{doc.get('doc_id')}: Milvus child chunk upsert skipped ({exc})"
                if fail_on_vector_error:
                    raise RuntimeError(message) from exc
                warnings.append(message)
                doc_warnings.append(message)

        _upsert_document_record(
            doc=doc,
            kb_id=kb_id,
            doc_id=doc_id,
            parent_count=len(parents),
            child_count=len(children),
            vector_count=doc_vector_upserts,
            warnings=doc_warnings,
            skipped=False,
        )

    return {
        "docs": len(docs),
        "skipped_docs": skipped_docs,
        "parents": total_parents,
        "children": total_children,
        "parent_upserts": total_parent_upserts,
        "vector_upserts": total_vector_upserts,
        "source_dir": source_label,
        "warnings": warnings,
    }


def ingest_directory(
    dir_path: str | None = None,
    kb_id: str = "kb_cs_college",
    *,
    write_vectors: bool = True,
    fail_on_vector_error: bool = False,
) -> dict[str, Any]:
    """
    目录批量入库。

    Parent chunks are upserted into MySQL. Child chunks are embedded and written to
    Milvus on a best-effort basis by default so MySQL ingestion still succeeds when
    the vector service is not ready during local development.
    """
    resolved_dir = resolve_ingest_dir(dir_path)
    docs = load_documents_from_dir(resolved_dir)
    return _ingest_documents(
        docs,
        kb_id=kb_id,
        source_label=str(resolved_dir),
        write_vectors=write_vectors,
        fail_on_vector_error=fail_on_vector_error,
    )


def ingest_uploaded_document(
    *,
    filename: str,
    data: bytes,
    kb_id: str = "kb_cs_college",
    write_vectors: bool = True,
    fail_on_vector_error: bool = False,
) -> dict[str, Any]:
    """Clean, chunk, and ingest one uploaded document."""
    doc = load_document_from_bytes(filename, data)
    doc.setdefault("metadata", {})["source_type"] = "upload"
    return _ingest_documents(
        [doc],
        kb_id=kb_id,
        source_label=f"upload:{filename}",
        write_vectors=write_vectors,
        fail_on_vector_error=fail_on_vector_error,
    )


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else None
    result = ingest_directory(path)
    print(f"Ingest complete: {result}")
