"""Knowledge-base document listing helpers."""

from __future__ import annotations

from sqlalchemy import desc, func, select

from app.core.database import get_db_session
from app.core.models import KbDocumentRecord


def list_kb_documents(kb_id: str = "kb_cs_college", limit: int = 100) -> list[dict]:
    """Return latest ingested documents for one knowledge base."""
    safe_limit = max(1, min(limit, 500))
    with get_db_session() as db:
        records = list(
            db.scalars(
                select(KbDocumentRecord)
                .where(KbDocumentRecord.kb_id == kb_id)
                .order_by(desc(KbDocumentRecord.updated_at))
                .limit(safe_limit)
            )
        )
        return [
            {
                "doc_id": record.doc_id,
                "kb_id": record.kb_id,
                "title": record.title,
                "source_name": record.source_name,
                "file_ext": record.file_ext,
                "source_type": record.source_type,
                "content_chars": record.content_chars,
                "parent_count": record.parent_count,
                "child_count": record.child_count,
                "vector_count": record.vector_count,
                "status": record.status,
                "warnings": record.warnings or [],
                "updated_at": record.updated_at.isoformat() if record.updated_at else "",
            }
            for record in records
        ]


def count_kb_documents(kb_id: str = "kb_cs_college") -> int:
    with get_db_session() as db:
        return int(
            db.scalar(
                select(func.count()).select_from(KbDocumentRecord).where(KbDocumentRecord.kb_id == kb_id)
            )
            or 0
        )
