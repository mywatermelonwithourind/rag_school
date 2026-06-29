"""File-level views and coordinated deletion across MySQL and Milvus."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db_session, get_session_factory
from app.core.models import KbDocumentRecord, ParentChunkRecord
from app.file_management.milvus_store import (
    count_vectors,
    count_vectors_by_file,
    delete_vectors,
    list_child_chunks,
    restore_vectors,
    snapshot_vectors,
)


class KbFileNotFoundError(LookupError):
    pass


class KbFileConsistencyError(RuntimeError):
    pass


def _iso(value: Any) -> str:
    return value.isoformat() if value else ""


def _file_type(record: KbDocumentRecord | None, original_name: str) -> str:
    suffix = record.file_ext if record else Path(original_name).suffix
    return (suffix or "unknown").lstrip(".").upper()


def _metadata_for_file(
    file_id: str,
    title: str,
    records: list[KbDocumentRecord],
    used_ids: set[str] | None = None,
) -> KbDocumentRecord | None:
    used = used_ids or set()
    exact = next((record for record in records if record.doc_id == file_id), None)
    if exact:
        return exact

    normalized_title = title.strip()
    return next(
        (
            record
            for record in records
            if record.doc_id not in used
            and (
                record.title.strip() == normalized_title
                or Path(record.source_name).stem.strip() == normalized_title
            )
        ),
        None,
    )


def _summary(
    *,
    file_id: str,
    title: str,
    metadata: KbDocumentRecord | None,
    parent_count: int,
    child_count: int,
    character_count: int,
    parent_created_at: Any = None,
) -> dict[str, Any]:
    original_name = metadata.source_name if metadata else (title or file_id)
    display_name = metadata.title if metadata else (title or Path(original_name).stem or file_id)
    if metadata and metadata.status == "failed":
        status = "failed"
    elif parent_count > 0 and child_count > 0:
        status = "ready"
    elif parent_count > 0 or child_count > 0:
        status = "partial"
    else:
        status = metadata.status if metadata else "partial"

    return {
        "file_id": file_id,
        "original_name": original_name,
        "display_name": display_name,
        "file_type": _file_type(metadata, original_name),
        "status": status,
        "parent_count": int(parent_count),
        "child_count": int(child_count),
        "character_count": int(character_count),
        "ingested_at": _iso(metadata.created_at if metadata else parent_created_at),
    }


def list_kb_files(kb_id: str = "kb_cs_college") -> list[dict[str, Any]]:
    vector_counts = count_vectors_by_file(kb_id)
    with get_db_session() as db:
        metadata_records = list(
            db.scalars(
                select(KbDocumentRecord)
                .where(KbDocumentRecord.kb_id == kb_id)
                .order_by(KbDocumentRecord.created_at.desc())
            )
        )
        parent_rows = db.execute(
            select(
                ParentChunkRecord.doc_id,
                func.max(ParentChunkRecord.title).label("title"),
                func.count(ParentChunkRecord.parent_chunk_id).label("parent_count"),
                func.coalesce(func.sum(func.char_length(ParentChunkRecord.content)), 0).label(
                    "character_count"
                ),
                func.min(ParentChunkRecord.created_at).label("created_at"),
            )
            .where(ParentChunkRecord.kb_id == kb_id)
            .group_by(ParentChunkRecord.doc_id)
        ).all()

    parent_by_file = {str(row.doc_id): row for row in parent_rows}
    canonical_ids = set(parent_by_file) | set(vector_counts)
    summaries: list[dict[str, Any]] = []
    used_metadata_ids: set[str] = set()

    for file_id in sorted(canonical_ids):
        parent = parent_by_file.get(file_id)
        title = str(parent.title or "") if parent else ""
        metadata = _metadata_for_file(file_id, title, metadata_records, used_metadata_ids)
        if metadata:
            used_metadata_ids.add(metadata.doc_id)
        summaries.append(
            _summary(
                file_id=file_id,
                title=title,
                metadata=metadata,
                parent_count=int(parent.parent_count) if parent else 0,
                child_count=vector_counts.get(file_id, 0),
                character_count=int(parent.character_count) if parent else 0,
                parent_created_at=parent.created_at if parent else None,
            )
        )

    for metadata in metadata_records:
        if metadata.doc_id in used_metadata_ids or metadata.doc_id in canonical_ids:
            continue
        summaries.append(
            _summary(
                file_id=metadata.doc_id,
                title=metadata.title,
                metadata=metadata,
                parent_count=0,
                child_count=0,
                character_count=0,
            )
        )

    return sorted(summaries, key=lambda item: item["ingested_at"], reverse=True)


def get_kb_file(file_id: str, *, include_children: bool = False) -> dict[str, Any]:
    with get_db_session() as db:
        parents = list(
            db.scalars(
                select(ParentChunkRecord)
                .where(ParentChunkRecord.doc_id == file_id)
                .order_by(
                    ParentChunkRecord.chunk_index,
                    ParentChunkRecord.created_at,
                    ParentChunkRecord.parent_chunk_id,
                )
            )
        )
        metadata_records = list(db.scalars(select(KbDocumentRecord)))

    title = str(parents[0].title or "") if parents else ""
    metadata = _metadata_for_file(file_id, title, metadata_records)
    vector_count = count_vectors(file_id)
    if not parents and metadata is None and vector_count == 0:
        raise KbFileNotFoundError(file_id)

    children_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if include_children:
        for child in list_child_chunks(file_id):
            children_by_parent[str(child.get("parent_chunk_id") or "")].append(
                {
                    "child_chunk_id": str(child.get("child_chunk_id") or ""),
                    "chunk_index": int(child.get("chunk_index") or 0),
                    "content": str(child.get("content") or ""),
                }
            )

    parent_items = [
        {
            "parent_chunk_id": parent.parent_chunk_id,
            "chunk_index": parent.chunk_index,
            "title": parent.title or "",
            "content": parent.content,
            "children": children_by_parent.get(parent.parent_chunk_id, []),
        }
        for parent in parents
    ]
    summary = _summary(
        file_id=file_id,
        title=title,
        metadata=metadata,
        parent_count=len(parents),
        child_count=vector_count,
        character_count=sum(len(parent.content) for parent in parents),
        parent_created_at=parents[0].created_at if parents else None,
    )
    return {
        **summary,
        "full_text": "\n\n".join(parent.content for parent in parents),
        "reconstruction_notice": "非原始文件，由父块按序拼接还原",
        "parents": parent_items,
    }


def _matching_metadata_ids(db: Session, file_id: str, title: str) -> set[str]:
    records = list(db.scalars(select(KbDocumentRecord)))
    matched = _metadata_for_file(file_id, title, records)
    ids = {file_id}
    if matched:
        ids.add(matched.doc_id)
    return ids


def _mark_deletion(file_id: str, title: str, metadata_ids: set[str], message: str) -> None:
    with get_db_session() as db:
        existing = db.get(KbDocumentRecord, file_id)
        if existing is None:
            linked = next(
                (
                    db.get(KbDocumentRecord, metadata_id)
                    for metadata_id in metadata_ids
                    if metadata_id != file_id
                ),
                None,
            )
            existing = KbDocumentRecord(
                doc_id=file_id,
                kb_id=linked.kb_id if linked else "kb_cs_college",
                title=linked.title if linked else (title or file_id),
                source_name=linked.source_name if linked else (title or file_id),
                file_ext=linked.file_ext if linked else "",
                source_type=linked.source_type if linked else "upload",
                content_chars=linked.content_chars if linked else 0,
                parent_count=linked.parent_count if linked else 0,
                child_count=linked.child_count if linked else 0,
                vector_count=linked.vector_count if linked else 0,
                status="partial",
                warnings=[message],
                meta={"file_management_marker": True},
            )
            db.add(existing)
        else:
            existing.status = "partial"
            existing.warnings = [*(existing.warnings or []), message]


def _restore_vector_snapshot(
    file_id: str,
    vector_snapshot: list[dict[str, Any]],
) -> tuple[bool, int, str | None]:
    try:
        restore_vectors(vector_snapshot)
        restored_count = count_vectors(file_id)
        return restored_count == len(vector_snapshot), restored_count, None
    except Exception as exc:
        return False, -1, str(exc)


def delete_kb_file(file_id: str) -> dict[str, Any]:
    with get_db_session() as db:
        parents = list(
            db.scalars(
                select(ParentChunkRecord)
                .where(ParentChunkRecord.doc_id == file_id)
                .order_by(ParentChunkRecord.chunk_index)
            )
        )
        title = str(parents[0].title or "") if parents else ""
        metadata_ids = _matching_metadata_ids(db, file_id, title)
        existing_metadata_ids = {
            item
            for item in metadata_ids
            if db.get(KbDocumentRecord, item) is not None
        }

    vector_snapshot = snapshot_vectors(file_id)
    before = {
        "parent_count": len(parents),
        "vector_count": len(vector_snapshot),
    }
    if before["parent_count"] == 0 and before["vector_count"] == 0 and not existing_metadata_ids:
        raise KbFileNotFoundError(file_id)

    _mark_deletion(
        file_id,
        title,
        metadata_ids,
        "delete_in_progress: 正在同步删除 Milvus 子块与 MySQL 父块",
    )
    metadata_ids.add(file_id)

    try:
        delete_vectors(file_id)
        remaining_vectors = count_vectors(file_id)
        if remaining_vectors != 0:
            raise RuntimeError(f"Milvus ????? {remaining_vectors} ???")
    except Exception as exc:
        restored, restored_count, restore_error = _restore_vector_snapshot(
            file_id,
            vector_snapshot,
        )
        marker = (
            f"delete_failed_milvus: {exc}; restored_vectors={restored_count}; "
            f"restore_error={restore_error or 'none'}"
        )
        _mark_deletion(file_id, title, metadata_ids, marker)
        if not restored:
            raise KbFileConsistencyError(
                "Milvus ???????????????MySQL ??????????"
            ) from exc
        raise KbFileConsistencyError(
            "Milvus ?????MySQL ???????????????"
        ) from exc

    factory = get_session_factory()
    db = factory()
    try:
        db.execute(delete(ParentChunkRecord).where(ParentChunkRecord.doc_id == file_id))
        db.execute(delete(KbDocumentRecord).where(KbDocumentRecord.doc_id.in_(metadata_ids)))
        db.flush()
        remaining_parents = int(
            db.scalar(
                select(func.count())
                .select_from(ParentChunkRecord)
                .where(ParentChunkRecord.doc_id == file_id)
            )
            or 0
        )
        if remaining_parents != 0:
            raise RuntimeError(f"MySQL 删除后仍有 {remaining_parents} 个父块")
        db.commit()
    except Exception as exc:
        db.rollback()
        restored, restored_count, restore_error = _restore_vector_snapshot(
            file_id,
            vector_snapshot,
        )
        _mark_deletion(
            file_id,
            title,
            metadata_ids,
            (
                f"delete_failed_mysql: {exc}; restored_vectors={restored_count}; "
                f"restore_error={restore_error or 'none'}"
            ),
        )
        if not restored:
            raise KbFileConsistencyError(
                "MySQL ????? Milvus ??????????????"
            ) from exc
        raise KbFileConsistencyError("MySQL ?????Milvus ?????????") from exc
    finally:
        db.close()

    with get_db_session() as verify_db:
        after_parent_count = int(
            verify_db.scalar(
                select(func.count())
                .select_from(ParentChunkRecord)
                .where(ParentChunkRecord.doc_id == file_id)
            )
            or 0
        )
        after_metadata_count = int(
            verify_db.scalar(
                select(func.count())
                .select_from(KbDocumentRecord)
                .where(KbDocumentRecord.doc_id.in_(metadata_ids))
            )
            or 0
        )
    after_vector_count = count_vectors(file_id)
    if after_parent_count or after_metadata_count or after_vector_count:
        _mark_deletion(
            file_id,
            title,
            metadata_ids,
            (
                "delete_postcheck_failed: "
                f"parents={after_parent_count}, metadata={after_metadata_count}, "
                f"vectors={after_vector_count}"
            ),
        )
        raise KbFileConsistencyError(
            "出库后复核失败: "
            f"parents={after_parent_count}, metadata={after_metadata_count}, "
            f"vectors={after_vector_count}"
        )

    return {
        "file_id": file_id,
        "status": "deleted",
        "before": before,
        "after": {
            "parent_count": after_parent_count,
            "vector_count": after_vector_count,
        },
    }
