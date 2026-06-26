"""Document ingestion API — data/admin entry."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.schemas import IngestRequest, IngestResponse
from app.data.ingest import ingest_directory, ingest_uploaded_document
from app.data.loader import SUPPORTED_DOCUMENT_SUFFIXES

router = APIRouter(prefix="/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)


@router.post("", response_model=IngestResponse)
async def ingest_documents(body: IngestRequest):
    """Trigger one-click document cleaning and ingestion."""
    try:
        result = await asyncio.to_thread(
            ingest_directory,
            body.dir_path,
            body.kb_id,
            write_vectors=body.write_vectors,
            fail_on_vector_error=body.fail_on_vector_error,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Document ingestion failed")
        raise HTTPException(status_code=500, detail=f"入库失败: {exc}") from exc

    return IngestResponse(**result)


@router.post("/upload", response_model=IngestResponse)
async def ingest_uploaded_file(
    file: UploadFile = File(...),
    kb_id: str = Form(default="kb_cs_college"),
    write_vectors: bool = Form(default=True),
    fail_on_vector_error: bool = Form(default=False),
):
    """Upload one local document, then clean/chunk/upsert it."""
    filename = file.filename or "uploaded_document"
    suffix = f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_DOCUMENT_SUFFIXES))
        raise HTTPException(status_code=400, detail=f"仅支持以下格式: {allowed}")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")

    try:
        result = await asyncio.to_thread(
            ingest_uploaded_document,
            filename=filename,
            data=data,
            kb_id=kb_id,
            write_vectors=write_vectors,
            fail_on_vector_error=fail_on_vector_error,
        )
    except Exception as exc:
        logger.exception("Uploaded document ingestion failed")
        raise HTTPException(status_code=500, detail=f"入库失败: {exc}") from exc

    return IngestResponse(**result)
