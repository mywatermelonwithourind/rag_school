"""Knowledge-base document list API."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.schemas import KbDocumentListResponse, KbDocumentSchema
from app.core.documents import count_kb_documents, list_kb_documents

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=KbDocumentListResponse)
async def list_documents(
    kb_id: str = Query(default="kb_cs_college", min_length=1, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
):
    items = list_kb_documents(kb_id=kb_id, limit=limit)
    return KbDocumentListResponse(
        total=count_kb_documents(kb_id=kb_id),
        items=[KbDocumentSchema(**item) for item in items],
    )
